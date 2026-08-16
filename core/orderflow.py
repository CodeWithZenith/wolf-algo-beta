"""
Wolf Algo — Order Flow CVD & Delta Absorption Module
======================================================
Computes real-time Cumulative Volume Delta (CVD) and detects institutional 
order flow absorption at SMC key levels (Order Blocks, IFVGs, Liquidity Sweeps).
Does NOT require external Bookmap subscription — calculates directly from live tick/bar data!
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict


def calculate_order_flow_cvd(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes Cumulative Volume Delta (CVD) and Volume Imbalance.
    
    Formula:
      - Estimated Buy Volume = Volume * ((Close - Low) / (High - Low + 1e-6))
      - Estimated Sell Volume = Volume * ((High - Close) / (High - Low + 1e-6))
      - Bar Delta = Buy Volume - Sell Volume
      - CVD = Cumulative Sum of Bar Delta
    """
    def _get_col(names):
        for n in names:
            if n in df.columns:
                return df[n]
        return None

    close = _get_col(['Close', 'close', 'c'])
    high = _get_col(['High', 'high', 'h'])
    low = _get_col(['Low', 'low', 'l'])
    volume = _get_col(['Volume', 'volume', 'v'])
    if volume is None:
        volume = pd.Series(1000.0, index=df.index)

    range_spread = (high - low).replace(0, 1e-6)
    buy_vol = volume * ((close - low) / range_spread)
    sell_vol = volume * ((high - close) / range_spread)

    bar_delta = buy_vol - sell_vol
    df['bar_delta'] = bar_delta
    df['cvd'] = bar_delta.cumsum()
    df['cvd_sma'] = df['cvd'].rolling(window=14, min_periods=1).mean()
    
    return df


def detect_delta_absorption(df: pd.DataFrame) -> Tuple[bool, bool, Dict[str, float]]:
    """
    Detects Institutional Delta Absorption:
      - Bullish Absorption: Price hits low, but CVD turns positive (Buyers absorbing sellers).
      - Bearish Absorption: Price hits high, but CVD turns negative (Sellers absorbing buyers).
    
    Returns:
      (is_bullish_absorption, is_bearish_absorption, metrics_dict)
    """
    df_of = calculate_order_flow_cvd(df)
    latest = df_of.iloc[-1]
    prev_4 = df_of.iloc[-5:-1]

    def _get_val(sr, names, default_val=0.0):
        for n in names:
            if n in sr.index:
                return sr[n]
        return default_val

    close = _get_val(latest, ['Close', 'close', 'c'])
    cvd_latest = latest['cvd']
    cvd_sma = latest['cvd_sma']
    bar_delta = latest['bar_delta']

    high_col = None
    for col in ['High', 'high', 'h']:
        if col in prev_4.columns:
            high_col = col
            break

    low_col = None
    for col in ['Low', 'low', 'l']:
        if col in prev_4.columns:
            low_col = col
            break

    recent_high = prev_4[high_col].max() if high_col else close
    recent_low = prev_4[low_col].min() if low_col else close

    # Bearish Absorption: Price testing high, but Delta is negative / declining
    is_bearish_absorption = (close >= recent_high * 0.9995) and (bar_delta < 0 or cvd_latest < cvd_sma)

    # Bullish Absorption: Price testing low, but Delta is positive / expanding
    is_bullish_absorption = (close <= recent_low * 1.0005) and (bar_delta > 0 or cvd_latest > cvd_sma)

    metrics = {
        "cvd_latest": float(cvd_latest),
        "cvd_sma": float(cvd_sma),
        "bar_delta": float(bar_delta),
        "absorption_score": 15.0 if (is_bullish_absorption or is_bearish_absorption) else 0.0
    }

    return is_bullish_absorption, is_bearish_absorption, metrics


class HawkesCascadeDetector:
    """
    Hawkes Self-Exciting Point Process Order-Flow Cascade Detector.
    Models self-exciting trade arrival intensity lambda(t):
      lambda(t) = mu + sum_{t_i < t} alpha * exp(-beta * (t - t_i))
    Detects institutional liquidation cascades & stop sweeps in real-time.
    """

    def __init__(self, mu: float = 0.1, alpha: float = 0.5, beta: float = 1.0):
        self.mu = mu        # Baseline intensity
        self.alpha = alpha  # Excitation impact per order event
        self.beta = beta    # Exponential decay rate

    def compute_cascade_intensity(self, df_ticks_or_bars: pd.DataFrame) -> Tuple[float, bool, Dict[str, float]]:
        """
        Calculates Hawkes Intensity lambda(t) across recent bar deltas / volumes.
        Returns: (hawkes_intensity, is_cascade_active, metrics_dict)
        """
        if len(df_ticks_or_bars) < 5:
            return self.mu, False, {"intensity": self.mu, "threshold": 2.5}

        volumes = df_ticks_or_bars['v'].values if 'v' in df_ticks_or_bars.columns else df_ticks_or_bars['volume'].values
        vol_mean = np.mean(volumes) + 1e-6
        normalized_events = volumes / vol_mean

        # Compute Hawkes Exponentially Decayed Self-Exciting Intensity Sum
        n = len(normalized_events)
        intensity = self.mu
        for i in range(n):
            time_diff = n - 1 - i
            excitation = self.alpha * normalized_events[i] * np.exp(-self.beta * time_diff)
            intensity += excitation

        # Cascade Threshold: Intensity >= 2.5x baseline
        threshold = 2.5 * self.mu
        is_cascade_active = intensity >= threshold

        metrics = {
            "hawkes_intensity": round(float(intensity), 3),
            "baseline_mu": round(self.mu, 3),
            "cascade_threshold": round(threshold, 3),
            "is_cascade_active": is_cascade_active
        }

        return float(intensity), is_cascade_active, metrics


hawkes_detector = HawkesCascadeDetector()
