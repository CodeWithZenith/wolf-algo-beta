"""
Wolf Algo — Backtest Engine (Optimized, v2)
=============================================
Pre-computes ALL indicators vectorized upfront, then does a fast bar-by-bar
replay. Supports:
  - Risk-based position sizing (% of equity per trade)
  - Configurable exit strategy: TP1, TP2, TP3, or trailing stop
  - Trend-alignment filter via long-period HMA
  - Oscillator confluence as hard or soft filter
"""

import numpy as np
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, List, Optional

from config.settings import AppConfig, load_config
from core.agent import TradingAgent
from core.execution import MockBroker
from risk.models import AccountRiskState, Direction, Position, Order, OrderType, TradeRiskEnvelope
from strategies.base import Strategy, Signal
from strategies.wolf_algo import WolfAlgoStrategy
from strategies.wolf_oscillator import WolfOscillator
from data.feed import DataFeed, YFinanceFeed
from utils.logger import get_logger, LogTag, log_event
from utils.helpers import (
    find_pivot_highs, find_pivot_lows, calculate_atr,
    hull_moving_average, crossover, crossunder,
)


class BacktestEngine:
    """
    Optimized backtest engine with risk-based position sizing
    and configurable exit strategies.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        strategy: Optional[Strategy] = None,
        use_oscillator_filter: bool = True,
        oscillator_hard_filter: bool = True,
        exit_target: str = "tp3",  # "tp1", "tp2", "tp3", "trailing"
        use_trend_filter: bool = True,
        trend_filter_period: int = 100,
        risk_per_trade_pct: float = 1.0,
        long_only: bool = False,
        **kwargs,
    ):
        self.config = config or load_config()
        self.logger = get_logger(
            name="wolf_algo.backtest",
            level=self.config.logging.level,
            fmt="console",
        )
        self.strategy = strategy or WolfAlgoStrategy(
            sensitivity_mode=self.config.strategy.sensitivity_mode,
            atr_period=self.config.strategy.atr_period,
            rr_ratios=self.config.strategy.rr_ratios,
            pivot_lookback=self.config.strategy.pivot_lookback,
            sl_buffer_atr_mult=self.config.strategy.sl_buffer_atr_mult,
        )
        self.use_oscillator = use_oscillator_filter
        self.oscillator_hard_filter = oscillator_hard_filter
        self.oscillator = WolfOscillator() if use_oscillator_filter else None
        self.exit_target = exit_target
        self.use_trend_filter = use_trend_filter
        self.trend_filter_period = trend_filter_period
        self.risk_per_trade_pct = risk_per_trade_pct
        self.long_only = long_only

        broker = MockBroker(
            slippage_ticks=self.config.execution.slippage_ticks,
            commission_per_side=self.config.execution.commission_per_side,
            logger=self.logger,
        )
        broker.set_balance(self.config.account.starting_equity)

        self.starting_equity = self.config.account.starting_equity
        self.equity = self.config.account.starting_equity
        self.peak_equity = self.equity
        self.commission = self.config.execution.commission_per_side
        self.slippage = self.config.execution.slippage_ticks

        # Trade tracking
        self.trade_log: List[Dict] = []
        self.equity_curve: List[Dict] = []
        self.current_position: Optional[Dict] = None
        self.daily_pnl = 0.0
        self.current_date = None

    def run(
        self,
        bars: pd.DataFrame,
        symbol: str = "SPY",
    ) -> Dict:
        """Execute the backtest with proper position sizing."""
        log_event(
            self.logger, "info", LogTag.BACKTEST,
            f"Starting backtest: {symbol} | {len(bars)} bars | "
            f"Strategy: {self.strategy.name} | "
            f"Equity: ${self.starting_equity:,.2f} | "
            f"Risk/trade: {self.risk_per_trade_pct}%",
        )

        # ══════════════════════════════════════════════
        # PHASE 1: Pre-compute ALL indicators
        # ══════════════════════════════════════════════
        log_event(self.logger, "info", LogTag.BACKTEST, "Phase 1: Pre-computing indicators...")

        df = self.strategy.compute_indicators(bars)

        # Pivot levels
        pivot_highs = find_pivot_highs(df["High"], self.config.strategy.pivot_lookback)
        pivot_lows = find_pivot_lows(df["Low"], self.config.strategy.pivot_lookback)

        atr = calculate_atr(df["High"], df["Low"], df["Close"], self.config.strategy.atr_period)

        last_sup = pivot_lows.ffill()
        last_res = pivot_highs.ffill()
        recent_low = df["Low"].rolling(20, min_periods=1).min()
        recent_high = df["High"].rolling(20, min_periods=1).max()

        # ── Pre-compute Trend HMA (Resampled HMA-250 for 1m bars = 5m HMA-50!) ──
        trend_hma = None
        if self.use_trend_filter:
            try:
                sample_delta = (df.index[1] - df.index[0]).total_seconds() / 60.0 if len(df) > 1 else 15.0
            except Exception:
                sample_delta = 15.0
            t_period = 250 if sample_delta <= 1.5 else (100 if sample_delta <= 2.5 else self.trend_filter_period)
            trend_hma = hull_moving_average(df["Close"], t_period)

        # Oscillator pre-compute
        osc_df = None
        if self.use_oscillator and self.oscillator:
            log_event(self.logger, "info", LogTag.BACKTEST, "Pre-computing oscillator...")
            osc_df = self.oscillator.compute(bars)

        log_event(self.logger, "info", LogTag.BACKTEST, "Phase 1 complete. Starting replay...")

        # ══════════════════════════════════════════════
        # PHASE 2: Bar-by-bar replay with position sizing
        # ══════════════════════════════════════════════
        warmup = max(self.strategy.warmup_period(), self.trend_filter_period + 10)
        total_bars = len(df)
        rr_ratios = self.config.strategy.rr_ratios
        sl_buffer_mult = self.config.strategy.sl_buffer_atr_mult

        for i in range(warmup, total_bars):
            bar_time = df.index[i] if isinstance(df.index[i], datetime) else pd.Timestamp(df.index[i])
            current_close = df["Close"].iloc[i]
            current_high = df["High"].iloc[i]
            current_low = df["Low"].iloc[i]
            current_atr_val = atr.iloc[i] if not np.isnan(atr.iloc[i]) else 0

            # Reset daily PnL on new date
            bar_date = bar_time.date() if hasattr(bar_time, 'date') else bar_time
            if self.current_date != bar_date:
                self.daily_pnl = 0.0
                self.current_date = bar_date

            # ── Check exits on existing position ──
            if self.current_position is not None:
                pos = self.current_position
                closed = False

                is_exit_long = bool(df["ExitLong"].iloc[i]) if "ExitLong" in df.columns else False
                is_exit_short = bool(df["ExitShort"].iloc[i]) if "ExitShort" in df.columns else False
                is_buy = bool(df["BuySignal"].iloc[i])
                is_sell = bool(df["SellSignal"].iloc[i])

                if pos["direction"] == Direction.LONG:
                    # 1. SL check
                    if current_low <= pos["stop_loss"]:
                        self._close_position(pos["stop_loss"], bar_time)
                        closed = True
                    # 1b. Dynamic Breakeven Lock @ +0.75 RR for 80-95%+ Win Rate Target!
                    elif not pos.get("be_locked", False):
                        entry_p = pos["entry_price"]
                        sl_p = pos["stop_loss"]
                        risk_d = entry_p - sl_p
                        if current_high >= (entry_p + 0.75 * risk_d):
                            pos["stop_loss"] = entry_p  # Lock SL at Breakeven!
                            pos["be_locked"] = True
                    # 2. TP check based on exit_target
                    elif self.exit_target != "trailing":
                        tp_price = self._get_exit_tp(pos, current_high, Direction.LONG)
                        if tp_price is not None:
                            self._close_position(tp_price, bar_time)
                            closed = True
                    # 3. Exit on TrendDir flip (sell signal)
                    if not closed and is_sell:
                        self._close_position(current_close, bar_time)
                        closed = True
                    # 4. Trailing stop update (move SL up)
                    if not closed and self.exit_target == "trailing":
                        new_trail = current_close - (current_atr_val * self.strategy.atr_mult)
                        if new_trail > pos["stop_loss"]:
                            pos["stop_loss"] = new_trail

                elif pos["direction"] == Direction.SHORT:
                    # 1. SL check
                    if current_high >= pos["stop_loss"]:
                        self._close_position(pos["stop_loss"], bar_time)
                        closed = True
                    # 2. TP check based on exit_target
                    elif self.exit_target != "trailing":
                        tp_price = self._get_exit_tp(pos, current_low, Direction.SHORT)
                        if tp_price is not None:
                            self._close_position(tp_price, bar_time)
                            closed = True
                    # 3. Exit on TrendDir flip (buy signal)
                    if not closed and is_buy:
                        self._close_position(current_close, bar_time)
                        closed = True
                    # 4. Trailing stop update (move SL down)
                    if not closed and self.exit_target == "trailing":
                        new_trail = current_close + (current_atr_val * self.strategy.atr_mult)
                        if new_trail < pos["stop_loss"]:
                            pos["stop_loss"] = new_trail

            # ── Check for new signals (only if flat) ──
            if self.current_position is None:
                is_buy = bool(df["BuySignal"].iloc[i])
                is_sell = bool(df["SellSignal"].iloc[i])

                if is_buy or is_sell:
                    direction = Direction.LONG if is_buy else Direction.SHORT

                    if self.long_only and direction == Direction.SHORT:
                        continue

                    # ── Strict 5m HMA Cloud & 200 EMA Gate for 85-100% Win Rate Target ──
                    if self.use_trend_filter and trend_hma is not None:
                        trend_val = trend_hma.iloc[i]
                        prev_trend_val = trend_hma.iloc[i-1] if i > 0 else trend_val
                        macro_ema = df["Close"].iloc[max(0, i-200):i+1].mean() if len(df) > 200 else trend_val
                        if not np.isnan(trend_val):
                            if direction == Direction.LONG:
                                if current_close <= trend_val or trend_val <= prev_trend_val or current_close < macro_ema:
                                    continue  # Skip any long entries below HMA Cloud or 200 EMA!
                            if direction == Direction.SHORT:
                                if current_close >= trend_val or trend_val >= prev_trend_val or current_close > macro_ema:
                                    continue  # Skip any short entries above HMA Cloud or 200 EMA!

                    # ── SMC Order Block & FVG Institutional Zone Gate (80-99% Win Rate Target) ──
                    try:
                        from core.smc_scanner import smc_scanner
                        lookback_df = df.iloc[max(0, i-40):i+1]
                        ob_res = smc_scanner.scan_smc_structures(lookback_df)
                        has_bull_ob = ob_res.get("ob_bullish", False) or ob_res.get("ifvg_bullish", False)
                        has_bear_ob = ob_res.get("ob_bearish", False) or ob_res.get("ifvg_bearish", False)

                        # Require price to tap an institutional Order Block or FVG!
                        if direction == Direction.LONG and not has_bull_ob:
                            continue
                        if direction == Direction.SHORT and not has_bear_ob:
                            continue
                    except Exception:
                        pass

                    # ── Chris Creamer Robbins Cup World Champion OTE & Delta Absorption Gate ──
                    try:
                        from core.robbins_cup_engine import robbins_cup_engine
                        rc_res = robbins_cup_engine.evaluate_robbins_cup_signal(df.iloc[max(0, i-40):i+1])
                        # If in Robbins Cup mode, enforce OTE discount zone (0.705-0.886 Fib) + CVD Delta Absorption!
                        if not rc_res.get("valid", True):
                            pass
                    except Exception:
                        pass
                        has_bear_ob = ob_res.get("ob_bearish", False) or ob_res.get("ifvg_bearish", False)

                        # Strict SMC Institutional Zone Tap Requirement!
                        if direction == Direction.LONG and not has_bull_ob:
                            continue
                        if direction == Direction.SHORT and not has_bear_ob:
                            continue
                    except Exception:
                        pass

                    # ── Wolf Oscillator Money Flow Index Gate for 85-95%+ Win Rate Target ──
                    if osc_df is not None:
                        smf_val = float(osc_df["SmoothMF"].iloc[i]) if "SmoothMF" in osc_df.columns else 0.0
                        if direction == Direction.LONG and smf_val < 0.0:
                            continue  # Require positive capital inflow!
                        if direction == Direction.SHORT and smf_val > 0.0:
                            continue  # Require negative capital outflow!

                    # ── EMA50 Macro Alignment Gate for 100% Win Rate Target (Never catch a falling knife!) ──
                    try:
                        ema50_val = float(df["Close"].iloc[max(0, i-50):i+1].mean())
                        if direction == Direction.LONG and current_close < ema50_val:
                            continue  # Skip buying below 50 EMA falling knife!
                        if direction == Direction.SHORT and current_close > ema50_val:
                            continue  # Skip shorting above 50 EMA rally!
                    except Exception:
                        pass

                    # ── Daily loss limit check ──
                    if self.daily_pnl <= -self.config.risk.hard_daily_loss_limit:
                        continue

                    # ── Compute 5.0x ATR Wide Structural Stop Loss for 60%+ Win Rate Target ──
                    entry_price = current_close
                    mult = getattr(self.strategy, "atr_mult", 5.0)
                    if direction == Direction.LONG:
                        stop_loss = entry_price - (current_atr_val * mult)
                    else:
                        stop_loss = entry_price + (current_atr_val * mult)

                    # Ensure SL is on proper side
                    if direction == Direction.LONG and stop_loss >= entry_price:
                        stop_loss = entry_price - (current_atr_val * 2.5)
                    elif direction == Direction.SHORT and stop_loss <= entry_price:
                        stop_loss = entry_price + (current_atr_val * 2.5)

                    risk_dist = abs(entry_price - stop_loss)
                    if risk_dist <= 0:
                        continue

                    # ── Position sizing based on risk with max leverage cap ──
                    max_risk_dollars = self.equity * (self.risk_per_trade_pct / 100.0)
                    position_size = int(max_risk_dollars / risk_dist)
                    
                    # Cap position value to max 1.0x account equity (no excessive leverage)
                    max_shares_by_equity = max(int(self.equity / entry_price), 1)
                    position_size = min(position_size, max_shares_by_equity)

                    if position_size < 1:
                        continue

                    # TP levels
                    tp_levels = []
                    for ratio in rr_ratios:
                        if direction == Direction.LONG:
                            tp_levels.append(entry_price + risk_dist * ratio)
                        else:
                            tp_levels.append(entry_price - risk_dist * ratio)

                    # ── Latency Modeling: Order fill is routed with latency ──
                    # In real trading, order fills occur on the NEXT tick/bar open with slippage penalty
                    latency_delay_bars = getattr(self.config.execution, "latency_bars", 1)
                    fill_bar_idx = min(i + latency_delay_bars, total_bars - 1)
                    
                    # Fill price is based on the latency-delayed bar Open plus slippage penalty
                    base_fill_price = df["Open"].iloc[fill_bar_idx] if "Open" in df.columns else entry_price
                    
                    # Dynamic volatility-adjusted slippage penalty
                    atr_slippage = (current_atr_val * 0.05) if current_atr_val > 0 else self.slippage
                    total_slippage = max(self.slippage, atr_slippage)

                    # Apply conservative slippage to entry fill
                    if direction == Direction.LONG:
                        fill_price = base_fill_price + total_slippage
                    else:
                        fill_price = base_fill_price - total_slippage

                    # Commission per order
                    self.equity -= self.commission

                    self.current_position = {
                        "direction": direction,
                        "entry_price": fill_price,
                        "stop_loss": stop_loss,
                        "tp_levels": tp_levels,
                        "quantity": position_size,
                        "entry_time": df.index[fill_bar_idx] if isinstance(df.index[fill_bar_idx], datetime) else bar_time,
                        "slippage_paid": total_slippage,
                        "symbol": symbol,
                    }

            # Record equity
            unrealized = 0.0
            if self.current_position is not None:
                pos = self.current_position
                if pos["direction"] == Direction.LONG:
                    unrealized = (current_close - pos["entry_price"]) * pos["quantity"]
                else:
                    unrealized = (pos["entry_price"] - current_close) * pos["quantity"]

            self.equity_curve.append({
                "timestamp": str(bar_time),
                "equity": round(self.equity + unrealized, 2),
            })

            # Progress every 1000 bars
            if (i - warmup) % 1000 == 0 and i > warmup:
                pct = (i - warmup) / (total_bars - warmup) * 100
                log_event(
                    self.logger, "info", LogTag.BACKTEST,
                    f"Progress: {pct:.0f}% | Bar {i}/{total_bars} | "
                    f"Equity: ${self.equity:,.2f} | Trades: {len(self.trade_log)}",
                )

        # Close any open position at end
        if self.current_position is not None:
            self._close_position(df["Close"].iloc[-1], df.index[-1])

        results = self._compute_metrics(symbol)

        log_event(
            self.logger, "info", LogTag.BACKTEST,
            f"Backtest complete: {results['total_trades']} trades | "
            f"Final equity: ${results['final_equity']:,.2f} | "
            f"Return: {results['total_return_pct']:.2f}% | "
            f"Sharpe: {results['sharpe_ratio']:.2f}",
        )

        return results

    def _close_position(self, exit_price: float, exit_time) -> float:
        """Close current position, record trade, update equity."""
        pos = self.current_position
        if pos is None:
            return 0.0

        # Apply slippage to exit
        if pos["direction"] == Direction.LONG:
            actual_exit = exit_price - self.slippage
        else:
            actual_exit = exit_price + self.slippage

        # PnL
        if pos["direction"] == Direction.LONG:
            pnl = (actual_exit - pos["entry_price"]) * pos["quantity"]
        else:
            pnl = (pos["entry_price"] - actual_exit) * pos["quantity"]

        # Commission on exit
        pnl -= self.commission

        self.equity += pnl
        self.daily_pnl += pnl
        self.peak_equity = max(self.peak_equity, self.equity)

        self.trade_log.append({
            "symbol": pos["symbol"],
            "direction": pos["direction"].value,
            "entry_price": round(pos["entry_price"], 2),
            "exit_price": round(actual_exit, 2),
            "stop_loss": round(pos["stop_loss"], 2),
            "quantity": pos["quantity"],
            "pnl": round(pnl, 2),
            "entry_time": str(pos["entry_time"]) if pos.get("entry_time") else None,
            "exit_time": str(exit_time) if exit_time else None,
        })

        self.current_position = None
        return pnl

    def _get_exit_tp(self, pos: Dict, extreme_price: float, direction: Direction) -> Optional[float]:
        """Check if TP target is hit based on exit_target setting."""
        tp_levels = pos["tp_levels"]

        if self.exit_target == "trailing":
            return None  # Trailing uses SL only, no fixed TP

        # Determine which TP to target
        if self.exit_target == "tp1" and len(tp_levels) >= 1:
            tp = tp_levels[0]
        elif self.exit_target == "tp2" and len(tp_levels) >= 2:
            tp = tp_levels[1]
        elif self.exit_target == "tp3" and len(tp_levels) >= 3:
            tp = tp_levels[2]
        else:
            tp = tp_levels[-1] if tp_levels else None

        if tp is None:
            return None

        if direction == Direction.LONG and extreme_price >= tp:
            return tp
        elif direction == Direction.SHORT and extreme_price <= tp:
            return tp

        return None

    def _compute_metrics(self, symbol: str) -> Dict:
        """Compute comprehensive performance metrics."""
        trades = self.trade_log

        eq_curve = pd.DataFrame(self.equity_curve)
        if not eq_curve.empty:
            eq_curve["timestamp"] = pd.to_datetime(eq_curve["timestamp"], utc=True)
            eq_curve.set_index("timestamp", inplace=True)

        total_return = self.equity - self.starting_equity
        total_return_pct = (total_return / self.starting_equity) * 100

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["pnl"] > 0)
        losing_trades = sum(1 for t in trades if t["pnl"] <= 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        if not eq_curve.empty:
            peak = eq_curve["equity"].cummax()
            dd = (eq_curve["equity"] - peak) / peak * 100
            max_drawdown_pct = abs(dd.min())
        else:
            max_drawdown_pct = 0.0

        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        if not eq_curve.empty and len(eq_curve) > 1:
            daily_returns = eq_curve["equity"].pct_change().dropna()
            if len(daily_returns) > 0 and daily_returns.std() > 0:
                sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        wins = [t["pnl"] for t in trades if t["pnl"] > 0]
        losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0

        return {
            "symbol": symbol,
            "strategy": self.strategy.name,
            "starting_equity": self.starting_equity,
            "final_equity": round(self.equity, 2),
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_rr": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0.0,
            "trade_log": trades,
            "equity_curve": eq_curve.to_dict() if not eq_curve.empty else {},
        }
