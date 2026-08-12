"""
Wolf Algo V1 — Strategy Implementation
========================================
Direct Python translation of the Pine Script Wolf Algo V1 indicator.

Core Logic:
  - 4-layer HMA Cloud Ribbon for trend structure
  - ATR-based volatility trailing stop for trend direction
  - Entry signals on trend direction crossover
  - Exit signals on price crossing back through cloud3
  - Stop-loss anchored to structural pivot support/resistance
  - TP levels at configurable R:R ratios (1:1, 2:1, 3:1)
  
Sensitivity Modes:
  - Scalper:    fast=8,  slow=21, ATR mult=1.8
  - Day Trader: fast=13, slow=34, ATR mult=2.5
  - Swing:      fast=21, slow=55, ATR mult=3.5
"""

import numpy as np
import pandas as pd
from typing import Tuple, List

from strategies.base import Strategy, Signal
from risk.models import Direction
from utils.helpers import (
    hull_moving_average,
    calculate_atr,
    find_pivot_highs,
    find_pivot_lows,
    crossover,
    crossunder,
)


# ──────────────────────────────────────────────────────────────
# Sensitivity mode parameters
# ──────────────────────────────────────────────────────────────
SENSITIVITY_PARAMS = {
    "scalper":     {"fast": 8,  "slow": 21, "atr_mult": 1.8},
    "day_trader":  {"fast": 13, "slow": 34, "atr_mult": 2.5},
    "swing_trader": {"fast": 21, "slow": 55, "atr_mult": 3.5},
}


class WolfAlgoStrategy(Strategy):
    """
    Wolf Algo V1 — Trend-following strategy with structural risk management.
    
    Translates the Pine Script indicator into an actionable Python strategy
    that outputs clean Signal objects for the agent pipeline.
    """

    def __init__(
        self,
        sensitivity_mode: str = "day_trader",
        atr_period: int = 14,
        rr_ratios: Tuple[float, ...] = (1.0, 2.0, 3.0),
        pivot_lookback: int = 10,
        sl_buffer_atr_mult: float = 0.2,
    ):
        params = SENSITIVITY_PARAMS.get(sensitivity_mode, SENSITIVITY_PARAMS["day_trader"])
        self.fast_len = params["fast"]
        self.slow_len = params["slow"]
        self.atr_mult = params["atr_mult"]
        self.atr_period = atr_period
        self.rr_ratios = rr_ratios
        self.pivot_lookback = pivot_lookback
        self.sl_buffer_atr_mult = sl_buffer_atr_mult
        self.sensitivity_mode = sensitivity_mode

    @property
    def name(self) -> str:
        return f"WolfAlgo_V1_{self.sensitivity_mode}"

    def warmup_period(self) -> int:
        return self.slow_len + self.atr_period + self.pivot_lookback + 20

    def evaluate(self, bars: pd.DataFrame, symbol: str = "") -> Signal:
        """
        Evaluate Wolf Algo strategy on the latest bar.
        
        Expects `bars` to contain full history up to current bar.
        Only the last row generates a signal.
        """
        if len(bars) < self.warmup_period():
            return Signal(direction=Direction.FLAT, symbol=symbol)

        # ── Compute indicators across full history ──
        close = bars["Close"]
        high = bars["High"]
        low = bars["Low"]

        # ATR
        atr = calculate_atr(high, low, close, self.atr_period)

        # HMA Cloud layers
        cloud1 = hull_moving_average(close, self.fast_len)
        mid1_len = max(int(round((self.fast_len + self.slow_len) * 0.33)), 2)
        mid2_len = max(int(round((self.fast_len + self.slow_len) * 0.66)), 2)
        cloud2 = hull_moving_average(close, mid1_len)
        cloud3 = hull_moving_average(close, mid2_len)
        cloud4 = hull_moving_average(close, self.slow_len)

        # ── Volatility Trailing Stop (replicates Pine Script logic) ──
        trend_dir, trail_stop = self._compute_trailing_stop(close, atr)

        # ── Entry Signals ──
        buy_signal = crossover(trend_dir, 0)
        sell_signal = crossunder(trend_dir, 0)

        # ── Exit Signals ──
        exit_long = (trend_dir == 1) & crossunder(close, cloud3)
        exit_short = (trend_dir == -1) & crossover(close, cloud3)

        # ── Check the LAST bar for a signal ──
        idx = len(bars) - 1

        if buy_signal.iloc[idx]:
            return self._build_entry_signal(
                Direction.LONG, bars, atr, idx, symbol
            )
        elif sell_signal.iloc[idx]:
            return self._build_entry_signal(
                Direction.SHORT, bars, atr, idx, symbol
            )

        return Signal(direction=Direction.FLAT, symbol=symbol)

    def compute_indicators(self, bars: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all Wolf Algo indicators and attach them as columns.
        Useful for backtesting and analysis.
        """
        df = bars.copy()
        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        df["ATR"] = calculate_atr(high, low, close, self.atr_period)

        df["Cloud1"] = hull_moving_average(close, self.fast_len)
        mid1_len = max(int(round((self.fast_len + self.slow_len) * 0.33)), 2)
        mid2_len = max(int(round((self.fast_len + self.slow_len) * 0.66)), 2)
        df["Cloud2"] = hull_moving_average(close, mid1_len)
        df["Cloud3"] = hull_moving_average(close, mid2_len)
        df["Cloud4"] = hull_moving_average(close, self.slow_len)

        trend_dir, trail_stop = self._compute_trailing_stop(close, df["ATR"])
        df["TrendDir"] = trend_dir
        df["TrailStop"] = trail_stop

        df["BuySignal"] = crossover(trend_dir, 0)
        df["SellSignal"] = crossunder(trend_dir, 0)
        df["ExitLong"] = (trend_dir == 1) & crossunder(close, df["Cloud3"])
        df["ExitShort"] = (trend_dir == -1) & crossover(close, df["Cloud3"])

        # Pivot levels
        df["PivotHigh"] = find_pivot_highs(high, self.pivot_lookback)
        df["PivotLow"] = find_pivot_lows(low, self.pivot_lookback)

        return df

    # ──────────────────────────────────────────────────────────
    # Private methods
    # ──────────────────────────────────────────────────────────

    def _compute_trailing_stop(
        self, close: pd.Series, atr: pd.Series
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Replicates Pine Script's volatility trailing stop logic.
        Returns (trend_direction, trail_stop) as Series.
        
        trend_dir:  1 = bullish, -1 = bearish
        trail_stop: Current trailing stop level
        """
        n = len(close)
        trend_dir = np.zeros(n)
        trail_stop = np.full(n, np.nan)

        for i in range(1, n):
            c = close.iloc[i]
            a = atr.iloc[i] if not np.isnan(atr.iloc[i]) else 0

            up_band = c - (self.atr_mult * a)
            down_band = c + (self.atr_mult * a)

            prev_stop = trail_stop[i - 1] if not np.isnan(trail_stop[i - 1]) else c
            prev_dir = trend_dir[i - 1]

            if prev_dir == 1:
                trail_stop[i] = max(up_band, prev_stop)
                if c < trail_stop[i]:
                    trend_dir[i] = -1
                    trail_stop[i] = down_band
                else:
                    trend_dir[i] = 1
            else:
                trail_stop[i] = min(down_band, prev_stop)
                if c > trail_stop[i]:
                    trend_dir[i] = 1
                    trail_stop[i] = up_band
                else:
                    trend_dir[i] = -1

        return pd.Series(trend_dir, index=close.index), pd.Series(trail_stop, index=close.index)

    def _build_entry_signal(
        self,
        direction: Direction,
        bars: pd.DataFrame,
        atr: pd.Series,
        idx: int,
        symbol: str,
    ) -> Signal:
        """
        Build a complete entry signal with structural SL and TP levels.
        SL is anchored to the nearest pivot support (longs) or resistance (shorts).
        """
        entry_price = bars["Close"].iloc[idx]
        current_atr = atr.iloc[idx] if not np.isnan(atr.iloc[idx]) else 0

        # Find structural support/resistance via pivots
        pivot_highs = find_pivot_highs(bars["High"], self.pivot_lookback)
        pivot_lows = find_pivot_lows(bars["Low"], self.pivot_lookback)

        # Lookback window for recent pivots
        lookback_start = max(0, idx - 40)
        recent_high = bars["High"].iloc[lookback_start:idx + 1]
        recent_low = bars["Low"].iloc[lookback_start:idx + 1]

        # Find last valid pivot
        last_sup = self._last_valid_pivot(pivot_lows, idx)
        last_res = self._last_valid_pivot(pivot_highs, idx)

        # Fallback to recent high/low
        recent_low_val = recent_low.min()
        recent_high_val = recent_high.max()

        sl_buffer = current_atr * self.sl_buffer_atr_mult

        if direction == Direction.LONG:
            # SL below support
            sup = last_sup if (
                last_sup is not None
                and (entry_price - last_sup) < current_atr * 3.0
                and (entry_price - last_sup) > 0
            ) else recent_low_val
            stop_loss = sup - sl_buffer
        else:
            # SL above resistance
            res = last_res if (
                last_res is not None
                and (last_res - entry_price) < current_atr * 3.0
                and (last_res - entry_price) > 0
            ) else recent_high_val
            stop_loss = res + sl_buffer

        # TP levels at R:R ratios
        risk_dist = abs(entry_price - stop_loss)
        tp_levels = []
        for ratio in self.rr_ratios:
            if direction == Direction.LONG:
                tp_levels.append(entry_price + (risk_dist * ratio))
            else:
                tp_levels.append(entry_price - (risk_dist * ratio))

        return Signal(
            direction=direction,
            entry_price=entry_price,
            stop_price=stop_loss,
            tp_levels=tp_levels,
            strength=0.8,  # Base confidence — can be enhanced with oscillator confluence
            symbol=symbol,
            metadata={
                "atr": current_atr,
                "risk_dist": risk_dist,
                "sensitivity": self.sensitivity_mode,
            },
        )

    @staticmethod
    def _last_valid_pivot(pivots: pd.Series, current_idx: int):
        """Find the most recent non-NaN pivot value before current index."""
        for i in range(current_idx - 1, -1, -1):
            val = pivots.iloc[i]
            if not np.isnan(val):
                return val
        return None
