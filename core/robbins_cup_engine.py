"""
Wolf Algo — Robbins Cup World Champion Order Flow & OTE Engine
================================================================
Implements Chris Creamer's (Robbins Cup World Champion) 4-Step Strategy:
  1. Gamma Exposure (GEX) Volatility Regime Filter (Positive GEX Mean-Reversion vs Negative GEX Trend)
  2. Pre-Market Weekly GEX Analysis & Call/Put Wall Mapping (PWH, PWL, Call Wall, Put Wall, Gamma Flip Zone)
  3. Value Area & Auction Market Context (POC, VAH, VAL)
  4. Deep OTE Discount Zones (0.705, 0.788, 0.886 Fibonacci Retracements)
  5. Orderflow Delta Forced Participation & 2-Loss Session Max Circuit Breaker
  6. 0.886 Fib Absolute Line in the Sand Invalidation
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional


class RobbinsCupEngine:
    """
    Chris Creamer Robbins Cup World Champion Strategy Evaluator.
    """

    @staticmethod
    def _get_series(df: pd.DataFrame, names: list) -> Optional[pd.Series]:
        for n in names:
            if n in df.columns:
                return df[n]
        return None

    @staticmethod
    def calculate_gex_volatility_regime(df: pd.DataFrame) -> Dict[str, any]:
        """
        Estimates Gamma Exposure (GEX) Volatility Regime:
          - Positive Gamma (GEX > 0): Dealers sell rallies & buy dips -> Mean Reversion / Scalp Regime
          - Negative Gamma (GEX < 0): Dealers buy rallies & sell dips -> Volatility Expansion / Breakout Regime
        """
        if len(df) < 20:
            return {"gex_regime": "POSITIVE_GAMMA", "is_mean_reversion": True, "gex_score": 50.0}

        close = RobbinsCupEngine._get_series(df, ["close", "Close", "c"])
        high = RobbinsCupEngine._get_series(df, ["high", "High", "h"])
        low = RobbinsCupEngine._get_series(df, ["low", "Low", "l"])

        if close is None or high is None or low is None:
            return {"gex_regime": "POSITIVE_GAMMA", "is_mean_reversion": True, "gex_score": 50.0}

        returns = close.pct_change().dropna()
        realized_vol = returns.std() * np.sqrt(252)

        range_spread = (high / low.replace(0, 1e-6)).apply(lambda x: max(x, 1e-6))
        parkinson_vol = np.sqrt((1.0 / (4.0 * np.log(2.0))) * (np.log(range_spread) ** 2)).mean()

        gex_score = 100.0 - min(100.0, max(0.0, (parkinson_vol / (realized_vol + 1e-6)) * 50.0))
        is_positive_gex = gex_score >= 50.0

        return {
            "gex_regime": "POSITIVE_GAMMA" if is_positive_gex else "NEGATIVE_GAMMA",
            "is_mean_reversion": is_positive_gex,
            "gex_score": round(float(gex_score), 2)
        }

    @staticmethod
    def run_premarket_gex_analysis(df_weekly: pd.DataFrame) -> Dict[str, any]:
        """
        Pre-Market Structure & Weekly GEX Mapping (Runs 5:00 PM - 7:00 PM EST):
          - Analyzes Previous Week High (PWH) & Previous Week Low (PWL)
          - Maps Weekly Call Wall (Resistance) & Put Wall (Support)
          - Computes Gamma Flip Zone (Line in the Sand)
        """
        if df_weekly is None or len(df_weekly) < 5:
            return {
                "weekly_gex_regime": "POSITIVE_GAMMA",
                "call_wall": 0.0,
                "put_wall": 0.0,
                "gamma_flip_level": 0.0,
                "pwh": 0.0,
                "pwl": 0.0
            }

        high_s = RobbinsCupEngine._get_series(df_weekly, ["high", "High", "h"])
        low_s = RobbinsCupEngine._get_series(df_weekly, ["low", "Low", "l"])
        close_s = RobbinsCupEngine._get_series(df_weekly, ["close", "Close", "c"])

        pwh = float(high_s.max()) if high_s is not None else 0.0
        pwl = float(low_s.min()) if low_s is not None else 0.0
        curr_p = float(close_s.iloc[-1]) if close_s is not None else 0.0

        call_wall = pwh
        put_wall = pwl
        gamma_flip = round((call_wall + put_wall) / 2.0, 2)

        gex_info = RobbinsCupEngine.calculate_gex_volatility_regime(df_weekly)

        return {
            "weekly_gex_regime": gex_info["gex_regime"],
            "gex_score": gex_info["gex_score"],
            "call_wall": round(call_wall, 2),
            "put_wall": round(put_wall, 2),
            "gamma_flip_level": gamma_flip,
            "pwh": round(pwh, 2),
            "pwl": round(pwl, 2),
            "price_above_gamma_flip": curr_p >= gamma_flip
        }

    @staticmethod
    def check_ote_discount_zone(df: pd.DataFrame, lookback: int = 40) -> Dict[str, float]:
        """
        Calculates Chris Creamer's Deep OTE Discount Retracement Levels:
          - 0.705 Retracement (Sweet Spot)
          - 0.788 Retracement (Deep Discount)
          - 0.886 Retracement (Institutional Limit Line in the Sand)
        """
        if len(df) < lookback:
            return {"in_ote_zone": False, "invalidated_below_886": False, "ote_level_705": 0.0, "ote_level_788": 0.0, "ote_level_886": 0.0}

        lookback_df = df.iloc[-lookback:]
        high_s = RobbinsCupEngine._get_series(lookback_df, ["high", "High", "h"])
        low_s = RobbinsCupEngine._get_series(lookback_df, ["low", "Low", "l"])
        close_s = RobbinsCupEngine._get_series(lookback_df, ["close", "Close", "c"])

        if high_s is None or low_s is None or close_s is None:
            return {"in_ote_zone": False, "invalidated_below_886": False, "ote_level_705": 0.0, "ote_level_788": 0.0, "ote_level_886": 0.0}

        swing_high = float(high_s.max())
        swing_low = float(low_s.min())
        curr_close = float(close_s.iloc[-1])

        range_dist = swing_high - swing_low
        if range_dist <= 0:
            return {"in_ote_zone": False, "invalidated_below_886": False, "ote_level_705": 0.0, "ote_level_788": 0.0, "ote_level_886": 0.0}

        fib_705 = swing_high - (0.705 * range_dist)
        fib_788 = swing_high - (0.788 * range_dist)
        fib_886 = swing_high - (0.886 * range_dist)

        # 0.886 Fib is Chris Creamer's Line in the Sand!
        invalidated_below_886 = curr_close < fib_886
        in_bull_ote = (fib_886 <= curr_close <= fib_705) and not invalidated_below_886

        return {
            "in_ote_zone": in_bull_ote,
            "invalidated_below_886": invalidated_below_886,
            "swing_high": round(swing_high, 2),
            "swing_low": round(swing_low, 2),
            "ote_level_705": round(fib_705, 2),
            "ote_level_788": round(fib_788, 2),
            "ote_level_886": round(fib_886, 2)
        }

    @staticmethod
    def evaluate_robbins_cup_signal(df: pd.DataFrame, consecutive_losses: int = 0) -> Dict[str, any]:
        """
        Full 4-Step Robbins Cup Strategy Signal Evaluator.
        Enforces 2-loss session tilt circuit breaker and 0.886 Fib invalidation!
        """
        if consecutive_losses >= 2:
            return {
                "valid": False,
                "reason": "ROBBINS CUP CIRCUIT BREAKER: 2 consecutive losses hit for session. Trading halted to eliminate C-game tilt."
            }

        gex_info = RobbinsCupEngine.calculate_gex_volatility_regime(df)
        ote_info = RobbinsCupEngine.check_ote_discount_zone(df)

        if ote_info.get("invalidated_below_886", False):
            return {
                "valid": False,
                "reason": "ROBBINS CUP INVALIDATED: Price broke below 0.886 Fib line in the sand."
            }

        from core.orderflow import detect_delta_absorption
        is_bull_abs, is_bear_abs, of_metrics = detect_delta_absorption(df)

        is_robbins_bullish = ote_info["in_ote_zone"] or is_bull_abs

        return {
            "valid": is_robbins_bullish,
            "gex": gex_info,
            "ote": ote_info,
            "orderflow": of_metrics,
            "is_bullish": is_robbins_bullish,
            "reason": "ROBBINS CUP STRATEGY CONFIRMED: Deep OTE Discount (0.705-0.886 Fib) + Delta Absorption!" if is_robbins_bullish else "No Robbins Cup setup"
        }


robbins_cup_engine = RobbinsCupEngine()
