"""
Wolf Algo — Helper Functions
==============================
Technical analysis primitives used across strategies and the backtest engine.
Includes HMA, ATR, pivot detection, and crossover/crossunder utilities.
"""

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from typing import Tuple


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def weighted_moving_average(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average (WMA)."""
    weights = np.arange(1, period + 1, dtype=float)
    return series.rolling(window=period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def hull_moving_average(series: pd.Series, period: int) -> pd.Series:
    """
    Hull Moving Average (HMA) — fast, low-lag trend filter.
    
    Formula:  HMA(n) = WMA( 2*WMA(n/2) - WMA(n), sqrt(n) )
    """
    half_period = max(int(period / 2), 1)
    sqrt_period = max(int(np.sqrt(period)), 1)

    wma_half = weighted_moving_average(series, half_period)
    wma_full = weighted_moving_average(series, period)
    diff = 2 * wma_half - wma_full
    return weighted_moving_average(diff, sqrt_period)


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range (ATR)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period, min_periods=1).mean()


# ---------------------------------------------------------------------------
# Wolf Algo V1 Oscillator (Hyper Wave + Smart Money Flow)
# ---------------------------------------------------------------------------

def calculate_wolf_oscillator(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    wave_len: int = 10,
    wave_smooth: int = 21,
    sig_len: int = 4,
    mf_len: int = 35,
    mf_smooth: int = 6
) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    Direct Python implementation of the Wolf Algo V1 Oscillator:
      - wave1: Hyper Wave Signal line (EMA of CI)
      - wave2: Hyper Wave Slow line (SMA of wave1)
      - smooth_mf: Smart Money Flow (-100 to +100 scale)
      - bull_reversal: Boolean series triggering at oversold bounces (wave1 <= -60)
      - bull_confluence: Boolean series where wave1 > wave2 AND smooth_mf > 0
    """
    ap = (high + low + close) / 3.0
    esa = ap.ewm(span=wave_len, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=wave_len, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d.replace(0, np.nan))
    wave1 = ci.ewm(span=wave_smooth, adjust=False).mean().fillna(0.0)
    wave2 = wave1.rolling(window=sig_len, min_periods=1).mean()

    # Money Flow Index (MFI) logic
    typical_price = ap
    money_flow = typical_price * (high - low)
    pos_flow = pd.Series(np.where(typical_price > typical_price.shift(1), money_flow, 0), index=close.index)
    neg_flow = pd.Series(np.where(typical_price < typical_price.shift(1), money_flow, 0), index=close.index)
    
    pos_mf = pos_flow.rolling(window=mf_len, min_periods=1).sum()
    neg_mf = neg_flow.rolling(window=mf_len, min_periods=1).sum()
    mfi_ratio = pos_mf / neg_mf.replace(0, np.nan)
    raw_mfi = 100.0 - (100.0 / (1.0 + mfi_ratio.fillna(1.0)))
    shift_mf = (raw_mfi * 2.0) - 100.0
    smooth_mf = shift_mf.rolling(window=mf_smooth, min_periods=1).mean().fillna(0.0)

    # Reversals & Confluence
    wave_cross_up = (wave1 > wave2) & (wave1.shift(1) <= wave2.shift(1))
    bull_reversal = wave_cross_up & (wave1 <= -60.0)
    bull_confluence = (wave1 > wave2) & (smooth_mf > 0.0)

    return wave1, wave2, smooth_mf, bull_reversal, bull_confluence


# ---------------------------------------------------------------------------
# Pivot Detection
# ---------------------------------------------------------------------------

def find_pivot_highs(
    high: pd.Series, order: int = 10
) -> pd.Series:
    """
    Detect local pivot highs using scipy argrelextrema.
    Returns a Series of pivot high values (NaN elsewhere).
    Pivots are confirmed `order` bars after they form.
    """
    values = high.values
    indices = argrelextrema(values, np.greater_equal, order=order)[0]
    result = pd.Series(np.nan, index=high.index)
    for idx in indices:
        result.iloc[idx] = values[idx]
    return result


def find_pivot_lows(
    low: pd.Series, order: int = 10
) -> pd.Series:
    """
    Detect local pivot lows using scipy argrelextrema.
    Returns a Series of pivot low values (NaN elsewhere).
    """
    values = low.values
    indices = argrelextrema(values, np.less_equal, order=order)[0]
    result = pd.Series(np.nan, index=low.index)
    for idx in indices:
        result.iloc[idx] = values[idx]
    return result


# ---------------------------------------------------------------------------
# Crossover / Crossunder
# ---------------------------------------------------------------------------

def crossover(a: pd.Series, b) -> pd.Series:
    """
    True when `a` crosses above `b`.
    `b` can be a Series or a scalar.
    """
    if isinstance(b, (int, float)):
        b = pd.Series(b, index=a.index)
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a: pd.Series, b) -> pd.Series:
    """
    True when `a` crosses below `b`.
    `b` can be a Series or a scalar.
    """
    if isinstance(b, (int, float)):
        b = pd.Series(b, index=a.index)
    return (a < b) & (a.shift(1) >= b.shift(1))


# ---------------------------------------------------------------------------
# Price & Timestamp Utilities
# ---------------------------------------------------------------------------

def format_price(value: float, decimals: int = 2) -> str:
    """Format a price to fixed decimal places."""
    return f"{value:.{decimals}f}"


def normalize_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame index is a timezone-aware UTC DatetimeIndex."""
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def resample_bars(
    df: pd.DataFrame, timeframe: str = "1h"
) -> pd.DataFrame:
    """
    Resample OHLCV bars to a higher timeframe.
    Expects columns: Open, High, Low, Close, Volume.
    """
    return df.resample(timeframe).agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()
