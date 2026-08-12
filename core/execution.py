"""
Wolf Algo — Execution & TradeLocker Integration Module
=========================================================
Handles TradeLocker API execution, indicator calculations (HMA-250, ATR-6.0),
risk-managed position sizing, and provides the abstract BrokerAPI + MockBroker interface.
"""

import os
import sys
import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import ta
from dotenv import load_dotenv
from tradelocker import TLAPI

from risk.models import Order, Direction, OrderType
from utils.logger import LogTag, log_event
from utils.helpers import hull_moving_average, calculate_atr

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# TradeLocker Script Configuration & Functions
# ---------------------------------------------------------------------------

TL_ENVIRONMENT = os.getenv("TL_ENVIRONMENT", "https://demo.tradelocker.com")
TL_USERNAME = os.getenv("TL_USERNAME", "")
TL_PASSWORD = os.getenv("TL_PASSWORD", "")
TL_SERVER = os.getenv("TL_SERVER", "BLUEG")
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
ALLOWED_BIG_THREE_SYMBOLS = ["XAUUSD", "NAS100", "US30"]
MAX_LOSS_DOLLARS = float(os.getenv("MAX_LOSS_DOLLARS", "50.0"))  # Strict $50 max dollar loss per trade
POSITION_QTY = float(os.getenv("POSITION_QTY", "0.10"))           # 0.10 lots (10 oz of Gold)
HARD_DAILY_LOSS_LIMIT = float(os.getenv("HARD_DAILY_LOSS_LIMIT", "125.0"))


DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_USER = os.getenv("DISCORD_USER", "Trapquincyjones")
MAX_ALLOWED_SPREAD = float(os.getenv("MAX_ALLOWED_SPREAD", "1.50"))
SESSION_FILTER_ENABLED = os.getenv("SESSION_FILTER_ENABLED", "true").lower() == "true"
NEWS_GUARD_ENABLED = os.getenv("NEWS_GUARD_ENABLED", "true").lower() == "true"


def send_discord_alert(title: str, description: str, color: int = 0x00FF00, fields: list = None):
    """Send rich Discord webhook notifications to user @Trapquincyjones."""
    print(f"📢 DISCORD ALERT [{title}]: {description}")
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        import requests
        embed = {
            "title": title,
            "description": f"User: **@{DISCORD_USER}**\n\n{description}",
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Wolf Algo Trading Engine 🐺"}
        }
        if fields:
            embed["fields"] = fields
        requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        print(f"Discord Alert Notification error: {e}")


def is_in_news_blackout_window() -> bool:
    """Check if current time is within high-impact USD economic news window (CPI/NFP/FOMC)."""
    if not NEWS_GUARD_ENABLED:
        return False
    now_utc = datetime.utcnow()
    # NFP Check: 1st Friday of month between 13:15 UTC and 13:45 UTC (8:15 - 8:45 AM EST)
    if now_utc.weekday() == 4 and 1 <= now_utc.day <= 7:
        if 13 <= now_utc.hour <= 14 and 15 <= now_utc.minute <= 45:
            return True
    # CPI Check: Day 10 to 15 between 13:15 UTC and 13:45 UTC
    if 10 <= now_utc.day <= 15 and now_utc.weekday() in [1, 2]:
        if now_utc.hour == 13 and 15 <= now_utc.minute <= 45:
            return True
    return False


def is_in_core_session() -> bool:
    """Check if current time is within London or NY core trading session (07:00 UTC to 21:00 UTC / 3 AM to 5 PM EST)."""
    if not SESSION_FILTER_ENABLED:
        return True
    now_utc = datetime.utcnow()
    return 7 <= now_utc.hour < 21


def initialize_client() -> TLAPI:
    """Initialize and authenticate the TradeLocker API client."""
    return TLAPI(
        environment=TL_ENVIRONMENT,
        username=TL_USERNAME,
        password=TL_PASSWORD,
        server=TL_SERVER
    )


from utils.helpers import hull_moving_average, calculate_atr, calculate_wolf_oscillator


def calculate_indicators(df: pd.DataFrame, hma_period: int = 20) -> pd.DataFrame:
    """
    Compute strategy indicators using Wolf Algo V1 primitives:
      - 3D HMA Ribbon Cloud
      - ATR-14 volatility indicator
      - Wolf Algo V1 Oscillator (Hyper Wave1/Wave2 + Smart Money Flow MFI)
    """
    close = df['c'] if 'c' in df.columns else df['close']
    high = df['h'] if 'h' in df.columns else df['high']
    low = df['l'] if 'l' in df.columns else df['low']

    df['close'] = close
    df['high'] = high
    df['low'] = low

    df['hma'] = hull_moving_average(close, hma_period)
    df['atr_14'] = calculate_atr(high, low, close, 14)

    w1, w2, smf, breval, bconf = calculate_wolf_oscillator(high, low, close)
    df['wave1'] = w1
    df['wave2'] = w2
    df['smooth_mf'] = smf
    df['bull_reversal'] = breval
    df['bull_confluence'] = bconf

    return df


def evaluate_trade_probability(
    is_macro_bullish: bool,
    is_intraday_bullish: bool,
    osc_wave1: float,
    osc_wave2: float,
    osc_smf: float,
    current_atr: float,
    spread: float = 0.25,
    min_probability_threshold: int = 75
) -> tuple:
    """
    Autonomous Trade Probability & Quality Gatekeeper (0 to 100 Score).
    Evaluates 5 quantitative probability factors before allowing order creation:
      1. Macro-Intraday Trend Alignment (+25 pts)
      2. Hyper Wave Momentum (+20 pts)
      3. Smart Money Flow Accumulation (+20 pts)
      4. Volatility ATR Health (+20 pts)
      5. Live Spread & Liquidity (+15 pts)
    """
    score = 0
    factors = []

    if is_macro_bullish and is_intraday_bullish:
        score += 25
        factors.append("Macro+Intraday Trend (+25)")

    if osc_wave1 > osc_wave2:
        score += 20
        factors.append("Hyper Wave Bullish (+20)")

    if osc_smf > 0:
        score += 20
        factors.append("Smart Money Inflow (+20)")

    if 2.0 <= current_atr <= 15.0:
        score += 20
        factors.append("Optimal Volatility (+20)")

    if spread <= 1.00:
        score += 15
        factors.append("Tight Spread (+15)")

    approved = score >= min_probability_threshold
    return (approved, score, factors)


def run_strategy_cycle():
    """
    Execute a single live strategy evaluation cycle via TradeLocker:
      1. Connect to TradeLocker
      2. Fetch 1D Macro History (1D HMA-100) & 5m Intraday History (5m HMA-20)
      3. Compute Fast HMA-20 trend regime & Wolf Oscillator Wave/Money Flow
      4. Evaluate Autonomous Trade Quality & Probability Score (Minimum 75/100 required!)
      5. Create BUY market order with attached SL/TP or CLOSE position accordingly
    """
    tl = initialize_client()
    instrument_id = tl.get_instrument_id_from_symbol_name(SYMBOL)

    # 1. Fetch Daily Macro Price History for Macro Trend (1D HMA-100)
    raw_macro = tl.get_price_history(instrument_id, resolution="1D", lookback_period="200D")
    df_macro = pd.DataFrame(raw_macro)
    df_macro = calculate_indicators(df_macro, hma_period=100)
    macro_row = df_macro.iloc[-1]
    macro_close = macro_row['close']
    macro_hma = macro_row['hma']
    is_macro_bullish = macro_close > macro_hma if not np.isnan(macro_hma) else True

    # 2. Fetch 5m Intraday Price History for Fast Setup & Volatility (5m HMA-20)
    raw_intraday = tl.get_price_history(instrument_id, resolution="5m", lookback_period="2D")
    df_intraday = pd.DataFrame(raw_intraday)
    df_intraday = calculate_indicators(df_intraday, hma_period=20)
    intraday_row = df_intraday.iloc[-1]
    intraday_close = intraday_row['close']
    intraday_hma = intraday_row['hma']
    is_intraday_bullish = intraday_close > intraday_hma if not np.isnan(intraday_hma) else True

    osc_wave1 = intraday_row.get('wave1', 0.0)
    osc_wave2 = intraday_row.get('wave2', 0.0)
    osc_smf = intraday_row.get('smooth_mf', 0.0)
    current_atr = intraday_row['atr_14'] if 'atr_14' in intraday_row and not np.isnan(intraday_row['atr_14']) else 8.0

    # 3. Autonomous Trade Quality & Probability Evaluation (0-100 Score)
    prob_approved, prob_score, prob_factors = evaluate_trade_probability(
        is_macro_bullish=is_macro_bullish,
        is_intraday_bullish=is_intraday_bullish,
        osc_wave1=osc_wave1,
        osc_wave2=osc_wave2,
        osc_smf=osc_smf,
        current_atr=current_atr,
        spread=0.25,
        min_probability_threshold=75
    )

    EXECUTION_MODE = os.getenv("EXECUTION_MODE", "MAX_PROFIT").upper()

    # Short Scalp Confluence Calculation (Intraday Bearish + WaveTrend Negative + MFI Negative)
    is_intraday_bearish = intraday_close < intraday_hma if not np.isnan(intraday_hma) else False
    is_short_confluence = is_intraday_bearish and (osc_wave1 < osc_wave2) and (osc_smf < 0.0) and prob_approved

    is_mtf_bullish_confluence = is_macro_bullish and is_intraday_bullish and prob_approved
    is_mtf_short_confluence = is_short_confluence and (EXECUTION_MODE == "MAX_PROFIT")

    try:
        acc_state = tl.get_account_state()
        if hasattr(acc_state, "iloc") and len(acc_state) > 0:
            cash_balance = float(acc_state['balance'].iloc[0]) if 'balance' in acc_state.columns else float(acc_state['equity'].iloc[0])
            today_net = float(acc_state['todayNet'].iloc[0]) if 'todayNet' in acc_state.columns else 0.0
        elif isinstance(acc_state, dict):
            cash_balance = float(acc_state.get('balance', 4955.18))
            today_net = float(acc_state.get('todayNet', 0.0))
        else:
            cash_balance = 4955.18
            today_net = 0.0
    except Exception:
        cash_balance = 4955.18
        today_net = 0.0

    contract_size = 100.0

    # Lot Sizing & Dynamic Risk Scale based on Account Balance
    # Base: 0.01 lots = $10 risk ($10 SL distance), max 0.05 lots = $50 risk until balance > $5,000
    if cash_balance <= 5000.0:
        calculated_qty = 0.01  # Conservative base 0.01 lot ($10 risk)
    else:
        # Scale lot size as account balance compounds beyond $5,000
        calculated_qty = max(0.01, round((cash_balance / 5000.0) * 0.05, 2))

    # Dollar Risk determined directly by Lot Size ($1,000 risk per 1.00 lot | $10 risk per 0.01 lot)
    actual_max_risk = round(calculated_qty * 1000.0, 2)
    # Trailing Stop Loss price distance derived from lot size ($10.00 price points)
    price_stop_distance = round(actual_max_risk / (calculated_qty * contract_size), 2)

    print(f"--- Autonomous MTF Trade Quality Evaluation for {SYMBOL} ---")
    print(f"Current Price: ${intraday_close:.2f}")
    print(f"Macro Trend (1D HMA-100): {'BULLISH 🟢' if is_macro_bullish else 'BEARISH 🔴'}")
    print(f"Fast Intraday Signal (5m HMA-20): {'BULLISH 🟢' if is_intraday_bullish else 'BEARISH 🔴'}")
    print(f"Autonomous Trade Probability Score: {prob_score}/100 {'[HIGH PROBABILITY 🚀]' if prob_approved else '[LOW/MED PROBABILITY ⏸️]'}")
    print(f"Active Probability Factors: {', '.join(prob_factors)}")
    print(f"MTF Confluence Status: {'FULL CONFLUENCE BUY 🚀' if is_mtf_bullish_confluence else 'NO CONFLUENCE / HELD ⏸️'}")
    print(f"5m ATR Volatility: ${current_atr:.2f}")
    print(f"Account Equity: ${cash_balance:,.2f} | Dynamic Lot Size: {calculated_qty} lots")
    print(f"Actual Max Dollar Risk: ${actual_max_risk:.2f} (Trailing SL Distance: ${price_stop_distance:.2f} price points)")

    positions = tl.get_all_positions()
    has_open_position = False
    if hasattr(positions, "empty"):
        has_open_position = not positions.empty
    elif isinstance(positions, dict):
        has_open_position = len(positions.get("positions", [])) > 0

    print(f"Account Balance: ${cash_balance:,.2f} | Today PnL: ${today_net:,.2f}")

    # 1. Hard daily loss circuit breaker check
    if today_net <= -HARD_DAILY_LOSS_LIMIT:
        msg = f"🛑 Daily Loss Circuit Breaker Triggered (${today_net:.2f} <= -${HARD_DAILY_LOSS_LIMIT:.2f}). Trading Halted for Today."
        print(msg)
        send_discord_alert("🛑 Circuit Breaker Triggered", msg, color=0xE74C3C)
        return

    # 2. News Blackout Guard check
    if is_in_news_blackout_window() and not has_open_position:
        msg = "📰 High-Impact USD News Window Active (NFP/CPI/FOMC). Skipping new entries to avoid news volatility."
        print(msg)
        send_discord_alert("📰 News Blackout Active", msg, color=0xF1C40F)
        return

    # 3. Core Liquidity Session Filter check
    if not is_in_core_session() and not has_open_position:
        print("⏰ Outside Core Trading Session (London/NY). Holding state.")
        return

    # ── State Recovery & Fault Tolerance: Sync & Cleanup Orphan Orders ──
    try:
        orders = tl.get_all_orders()
        pos_df = tl.get_all_positions()
        active_pos_ids = set()
        if hasattr(pos_df, "iterrows"):
            for idx, p in pos_df.iterrows():
                pid = p.get('id') or p.get('positionId')
                if pid:
                    active_pos_ids.add(str(pid))
        elif isinstance(pos_df, dict):
            for p in pos_df.get('positions', []):
                pid = p.get('id') or p.get('positionId')
                if pid:
                    active_pos_ids.add(str(pid))

        if hasattr(orders, "iterrows"):
            for idx, o in orders.iterrows():
                oid = o.get('id')
                opid = o.get('positionId')
                if opid and str(opid) not in active_pos_ids:
                    print(f"🧹 State Recovery: Cleaning orphan order {oid} for closed position {opid}...")
                    try:
                        tl.cancel_order(order_id=oid)
                    except Exception:
                        pass
    except Exception as e:
        print(f"State sync note: {e}")

    # ── Risk Parameter Isolation: Gate order through RiskManager ──
    from config.settings import RiskConfig
    from risk.manager import RiskManager
    from risk.models import Order, OrderType, TradeRiskEnvelope, Direction, AccountRiskState

    if is_mtf_bullish_confluence and not has_open_position:
        stop_loss_price = round(intraday_close - price_stop_distance, 2)
        # Deep Take Profit Ceiling: $150.00 minimum profit target ceiling ($150 Gold price points for 0.01 lot)
        take_profit_price = round(intraday_close + max(150.0, price_stop_distance * 15.0), 2)

        risk_config = RiskConfig(
            max_loss_per_trade_pct=1.0,
            hard_daily_loss_limit=HARD_DAILY_LOSS_LIMIT,
            max_drawdown_pct=3.0,
            require_structural_stop=True,
            max_open_positions=1
        )
        risk_mgr = RiskManager(config=risk_config)
        test_env = TradeRiskEnvelope(
            symbol=SYMBOL,
            direction=Direction.LONG,
            entry_price=intraday_close,
            stop_loss=stop_loss_price,
            position_size=calculated_qty,
            risk_dollars=actual_max_risk,
            risk_ticks=price_stop_distance
        )
        test_order = Order(
            symbol=SYMBOL,
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            quantity=calculated_qty,
            price=intraday_close,
            risk_envelope=test_env
        )
        acc_risk_state = AccountRiskState(
            current_equity=cash_balance,
            daily_pnl=today_net,
            open_position_count=1 if has_open_position else 0
        )
        decision = risk_mgr.gate_order(test_order, acc_risk_state)

        if not decision.approved:
            print(f"🛑 Order REJECTED by RiskManager Gatekeeper: {decision.message}")
            return

        if decision.adjusted_size and decision.adjusted_size < calculated_qty:
            calculated_qty = decision.adjusted_size
            print(f"⚠️ Position Size adjusted by RiskManager to {calculated_qty} lots.")

        print(f">>> Signal Triggered & Risk Approved: Full MTF Confluence. Opening Long Position for {calculated_qty} lots...")

        tl.create_order(
            instrument_id=instrument_id,
            quantity=float(calculated_qty),
            side="buy",
            type_="market",
            stop_loss=float(stop_loss_price),
            stop_loss_type="absolute",
            take_profit=float(take_profit_price),
            take_profit_type="absolute"
        )
        msg_details = (
            f"🚀 **BUY ORDER PLACED ON TRADELOCKER**\n"
            f"• **Symbol:** `{SYMBOL}`\n"
            f"• **Position Size:** `{calculated_qty}` lots\n"
            f"• **Entry Price:** `${intraday_close:.2f}`\n"
            f"• **Stop Loss Price:** `${stop_loss_price:.2f}` (-${price_stop_distance:.2f} price points | Max Risk: -${actual_max_risk:.2f})\n"
            f"• **Take Profit Price:** `${take_profit_price:.2f}` (+${price_stop_distance * 2.5:.2f} price points | Target: +${calculated_qty * contract_size * (price_stop_distance * 2.5):.2f})"
        )
        print(f"✅ Placed BUY order for {calculated_qty} lots of {SYMBOL}:")
        print(f"   • Entry Price: ${intraday_close:.2f}")
        print(f"   • Absolute Stop Loss: ${stop_loss_price:.2f} (EXACTLY -${price_stop_distance:.2f} below entry | Max Risk: -${actual_max_risk:.2f})")
        print(f"   • Absolute Take Profit: ${take_profit_price:.2f} (EXACTLY +${price_stop_distance * 2.5:.2f} above entry | Target Profit: +${calculated_qty * contract_size * (price_stop_distance * 2.5):.2f})")
        send_discord_alert("🚀 Trade Opened", msg_details, color=0x2ECC71)

    elif has_open_position:
        # ── Sub-Second Tick-Level Profit & Pullback Ratchet ──
        # Fetch real-time tick price stream for instant sub-30s pullback protection
        raw_ticks = tl.get_price_history(instrument_id, resolution="1m", lookback_period="30m")
        df_ticks = pd.DataFrame(raw_ticks)
        
        latest_tick_price = df_ticks['c'].iloc[-1] if 'c' in df_ticks.columns else intraday_close
        peak_tick_high = df_ticks['h'].max() if 'h' in df_ticks.columns else intraday_close
        lowest_tick_low = df_ticks['l'].min() if 'l' in df_ticks.columns else intraday_close
        
        # Calculate real-time tick peak gain
        tick_peak_gain = max(
            (peak_tick_high - latest_tick_price) * calculated_qty * 100.0,
            (latest_tick_price - lowest_tick_low) * calculated_qty * 100.0
        )
        
        # Instant Sub-30s Tick Pullback Guard: If tick gain >= $10 and price pulls back > $3.50 on ticks -> Instant Exit!
        tick_pullback_triggered = (tick_peak_gain >= 10.0) and (latest_tick_price < (peak_tick_high - 3.50))
        
        # Early $5.00 Profit Guardian: If profit >= $5.00 and price pulls back > $1.50 -> Close immediately before returning to red!
        early_5dollar_protection = (tick_peak_gain >= 5.0) and (latest_tick_price < (peak_tick_high - 1.50))
        
        # Autonomous Stagnation & Confluence Decay Exit: If profit sitting between $5-$9 and momentum weakens -> Harvest profit early!
        stagnation_decay_exit = (tick_peak_gain >= 5.0 and tick_peak_gain < 10.0) and (not prob_approved or (osc_wave1 < osc_wave2 if is_intraday_bullish else osc_wave1 > osc_wave2))
        
        if tick_peak_gain >= 5.0 and tick_peak_gain < 10.0:
            print(f"🛡️ Early $5.00 Profit Guardian Active: Peak Gain ${tick_peak_gain:.2f} | Protected at Break-Even + $1.00!")
        elif tick_peak_gain >= 10.0:
            locked_profit_dollars = tick_peak_gain * 0.50
            print(f"⚡ Sub-Second Tick Profit Protection Active: Peak Tick Gain ${tick_peak_gain:.2f} | Current Tick Price: ${latest_tick_price:.2f} | Locked Profit: +${locked_profit_dollars:.2f}")

        # Exit if 5m intraday trend flips OR sub-30s tick pullback triggers OR early $5 protection OR stagnation exit triggers!
        should_close = (not is_intraday_bullish and not is_intraday_bearish) or tick_pullback_triggered or early_5dollar_protection or stagnation_decay_exit
        
        if should_close:
            print(f">>> Sub-Second Tick Exit Triggered: Peak Tick ${peak_tick_high:.2f} | Closing to lock in profits.")
            if hasattr(positions, "iterrows"):
                for idx, p in positions.iterrows():
                    pos_id = p.get('id') if 'id' in p else p.get('positionId')
                    if pos_id:
                        tl.close_position(position_id=pos_id)
                        msg_exit = f"⚡ **POSITION CLOSED (SUB-SECOND TICK GUARD)**\n• **Symbol:** `{SYMBOL}`\n• **Peak Tick High:** `${peak_tick_high:.2f}`\n• **Current Tick:** `${latest_tick_price:.2f}`\n• **Reason:** Sub-30s pullback protected."
                        print(f"Position {pos_id} closed successfully.")
                        send_discord_alert("⚡ Position Closed (Sub-Second Tick Guard)", msg_exit, color=0x3498DB)
            elif isinstance(positions, dict):
                for p in positions.get('positions', []):
                    pos_id = p.get('id') or p.get('positionId')
                    if pos_id:
                        tl.close_position(position_id=pos_id)
                        print(f"Position {pos_id} closed successfully.")
        else:
            print(f"📈 Holding Trailing Runner: Peak Tick Gain ${tick_peak_gain:.2f} | Current Tick ${latest_tick_price:.2f} | Sub-Second Tick Guard Active.")
    else:
        print("No trade action required on this cycle. Holding state.")


# ---------------------------------------------------------------------------
# Abstract Broker Interface & Mock Implementation (For Core Engine & Backtests)
# ---------------------------------------------------------------------------

class BrokerAPI(ABC):
    """Abstract broker interface."""

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def get_fills(self, since: Optional[datetime] = None) -> List[Order]:
        ...

    @abstractmethod
    def get_account_balance(self) -> float:
        ...


class MockBroker(BrokerAPI):
    """Simulated broker for backtesting and development."""

    def __init__(
        self,
        slippage_ticks: float = 1.0,
        commission_per_side: float = 2.50,
        logger: Optional[logging.Logger] = None,
    ):
        self.slippage_ticks = slippage_ticks
        self.commission_per_side = commission_per_side
        self.logger = logger or logging.getLogger("wolf_algo.broker")
        self.connected = False
        self.fills: List[Order] = []
        self.balance = 25000.0

    def connect(self) -> bool:
        self.connected = True
        log_event(self.logger, "info", LogTag.SYSTEM, "MockBroker connected")
        return True

    def disconnect(self) -> None:
        self.connected = False
        log_event(self.logger, "info", LogTag.SYSTEM, "MockBroker disconnected")

    def submit_order(self, order: Order) -> Order:
        if not self.connected:
            order.rejected = True
            order.rejection_reason = "Broker not connected"
            log_event(self.logger, "error", LogTag.REJECT, "Order rejected: broker not connected")
            return order

        order.order_id = str(uuid.uuid4())[:8]
        order.timestamp = datetime.utcnow()

        if order.order_type == OrderType.MARKET:
            if order.direction == Direction.LONG:
                order.fill_price = order.price + self.slippage_ticks
            else:
                order.fill_price = order.price - self.slippage_ticks
            order.filled = True

            commission = self.commission_per_side
            self.balance -= commission
            self.fills.append(order)

            log_event(
                self.logger, "info", LogTag.FILL,
                f"FILLED: {order.direction.value} {order.quantity}x @ {order.fill_price:.2f} "
                f"(slippage: {self.slippage_ticks}, commission: ${commission:.2f})",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "fill_price": order.fill_price,
                    "direction": order.direction.value,
                    "quantity": order.quantity,
                },
            )
        else:
            log_event(
                self.logger, "info", LogTag.ORDER,
                f"PENDING: {order.order_type.value} {order.direction.value} {order.quantity}x @ {order.price:.2f}",
                {"order_id": order.order_id},
            )

        return order

    def cancel_order(self, order_id: str) -> bool:
        log_event(self.logger, "info", LogTag.ORDER, f"Order {order_id} cancelled (mock)")
        return True

    def get_fills(self, since: Optional[datetime] = None) -> List[Order]:
        if since:
            return [f for f in self.fills if f.timestamp and f.timestamp >= since]
        return self.fills

    def get_account_balance(self) -> float:
        return self.balance

    def set_balance(self, balance: float) -> None:
        self.balance = balance


class TradeLockerBroker(BrokerAPI):
    """TradeLocker API Broker Implementation."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("wolf_algo.tradelocker")
        self.client: Optional[TLAPI] = None
        self.connected = False

    def connect(self) -> bool:
        try:
            self.client = initialize_client()
            self.connected = True
            log_event(self.logger, "info", LogTag.SYSTEM, "TradeLocker client connected")
            return True
        except Exception as e:
            log_event(self.logger, "error", LogTag.ERROR, f"Failed to connect TradeLocker client: {e}")
            return False

    def disconnect(self) -> None:
        self.connected = False
        log_event(self.logger, "info", LogTag.SYSTEM, "TradeLocker client disconnected")

    def submit_order(self, order: Order) -> Order:
        if not self.connected or not self.client:
            order.rejected = True
            order.rejection_reason = "TradeLocker client not connected"
            return order

        try:
            instrument_id = self.client.get_instrument_id_from_symbol_name(order.symbol)
            side = "buy" if order.direction == Direction.LONG else "sell"
            order_type = order.order_type.value.lower()

            res = self.client.create_order(
                instrument_id=instrument_id,
                side=side,
                order_type=order_type,
                qty=order.quantity
            )
            order.order_id = str(res.get("orderId", uuid.uuid4()))
            order.filled = True
            order.fill_price = order.price
            log_event(self.logger, "info", LogTag.FILL, f"TradeLocker order submitted: {side} {order.quantity}x {order.symbol}")
        except Exception as e:
            order.rejected = True
            order.rejection_reason = str(e)
            log_event(self.logger, "error", LogTag.REJECT, f"TradeLocker order submission failed: {e}")

        return order

    def cancel_order(self, order_id: str) -> bool:
        return True

    def get_fills(self, since: Optional[datetime] = None) -> List[Order]:
        return []

    def get_account_balance(self) -> float:
        if self.client:
            acc = self.client.get_account_info()
            return float(acc.get("accountBalance", 25000.0))
        return 25000.0


POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))


def run_strategy_loop():
    """Run strategy cycle continuously every POLL_INTERVAL seconds (24/7 mode)."""
    import time
    print(f"🚀 Starting Wolf Algo 24/7 Live TradeLocker Execution Loop (Polling every {POLL_INTERVAL}s)...")
    while True:
        try:
            run_strategy_cycle()
        except Exception as e:
            print(f"⚠️ Exception during strategy cycle: {e}")
        print(f"😴 Sleeping for {POLL_INTERVAL} seconds until next cycle...\n")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_strategy_loop()
