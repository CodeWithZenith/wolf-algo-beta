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
    df = df.copy()
    close = df['c'] if 'c' in df.columns else df['close']
    high = df['h'] if 'h' in df.columns else df['high']
    low = df['l'] if 'l' in df.columns else df['low']
    volume = df['v'] if 'v' in df.columns else df.get('volume', pd.Series(1000, index=df.index))

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
    if len(df) < 5:
        return False, False, {"cvd_delta": 0.0, "absorption_score": 0.0}

    df_of = calculate_order_flow_cvd(df)
    latest = df_of.iloc[-1]
    prev_4 = df_of.iloc[-5:-1]

    close = latest['close']
    cvd_latest = latest['cvd']
    cvd_sma = latest['cvd_sma']
    bar_delta = latest['bar_delta']

    recent_high = prev_4['high'].max()
    recent_low = prev_4['low'].min()

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
