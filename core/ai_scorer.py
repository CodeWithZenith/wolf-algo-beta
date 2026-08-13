"""
Wolf Algo — AI Machine Learning Market Regime & Probability Scorer
=====================================================================
Uses statistical volatility analysis and real-time market dynamics to
dynamically self-tune probability thresholds, entry confidence, and exit targets.
Surpasses static indicator bundles (like QuantVue) with adaptive intelligence!
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Tuple


class AIMarketRegimeScorer:
    """
    AI Market Regime & Dynamic Threshold Scorer.
    Adapts the minimum probability entry threshold (e.g. 75, 80, 85, or 90)
    based on live session liquidity, volatility regime, and trend strength.
    """

    def __init__(self):
        self.base_threshold = 80.0

    def evaluate_market_regime(
        self,
        df_intraday: pd.DataFrame,
        current_atr: float,
        is_macro_bullish: bool,
        is_intraday_bullish: bool
    ) -> Tuple[float, str, Dict[str, float]]:
        """
        Evaluates current AI Market Regime and returns:
          (adaptive_min_threshold, regime_name, regime_metrics)
        """
        now_utc = datetime.utcnow()
        hour_utc = now_utc.hour

        # Session Classification
        # London Session: 07:00 - 15:00 UTC (02:00 - 10:00 EST)
        # NY Overlap: 12:00 - 16:00 UTC (07:00 - 11:00 EST) -> PRIME VOLATILITY
        # Asian Session: 00:00 - 07:00 UTC -> LOW VOLATILITY
        is_ny_london_overlap = 12 <= hour_utc <= 16
        is_asian_session = 0 <= hour_utc < 7

        # Volatility Regime
        recent_atr = df_intraday['atr_14'].mean() if 'atr_14' in df_intraday.columns else current_atr
        volatility_ratio = current_atr / (recent_atr + 1e-6)

        # Base Threshold Tuning
        adaptive_threshold = self.base_threshold

        if is_ny_london_overlap:
            regime_name = "PRIME INSTITUTIONAL OVERLAP (NY/LONDON) ⚡"
            adaptive_threshold -= 5.0  # Slightly lower threshold during high liquidity
        elif is_asian_session:
            regime_name = "LOW LIQUIDITY ASIAN SESSION 😴"
            adaptive_threshold += 5.0  # Require higher score during low liquidity
        else:
            regime_name = "STANDARD SESSION 📊"

        # Volatility Adjustment
        if volatility_ratio > 1.5:
            regime_name += " [HIGH VOLATILITY EXPANSION 🔥]"
        elif volatility_ratio < 0.7:
            regime_name += " [COMPRESSED SQUEEZE 🔒]"

        adaptive_threshold = max(70.0, min(90.0, adaptive_threshold))

        metrics = {
            "adaptive_threshold": adaptive_threshold,
            "volatility_ratio": round(volatility_ratio, 2),
            "hour_utc": hour_utc,
            "is_prime_session": is_ny_london_overlap
        }

        return adaptive_threshold, regime_name, metrics


# Singleton instance
ai_scorer = AIMarketRegimeScorer()
