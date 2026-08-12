"""
Wolf Oscillator — Strategy Implementation
============================================
Direct Python translation of the Pine Script Wolf Algo V1 Oscillator.

Core Logic:
  - WaveTrend (Hyper Wave): EMA-smoothed CI oscillator + signal line
  - Smart Money Flow: Normalized MFI mapped to oscillator scale
  - Reversal Detection: Cross in OB/OS zones
  - Confluence Logic: Wave + MFI agreement for signal strength boost
  
This oscillator is used as a FILTER/CONFIRMER alongside Wolf Algo V1.
It does not produce entry signals on its own but enhances signal confidence.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Tuple


@dataclass
class OscillatorState:
    """Current oscillator readings for a single bar."""
    wave1: float = 0.0          # Fast wave (hyper wave signal)
    wave2: float = 0.0          # Slow wave (signal line)
    money_flow: float = 0.0     # Smoothed normalized MFI
    is_overbought: bool = False
    is_oversold: bool = False
    bull_reversal: bool = False
    bear_reversal: bool = False
    bull_confluence: bool = False
    bear_confluence: bool = False
    confluence_strength: float = 0.0  # -1.0 to 1.0


class WolfOscillator:
    """
    Wolf Oscillator — momentum and money flow confluence filter.
    
    Use alongside WolfAlgoStrategy to confirm or filter signals:
      - Bull confluence = wave bullish + money flow positive → boost LONG confidence
      - Bear confluence = wave bearish + money flow negative → boost SHORT confidence
      - Reversals in OB/OS zones flag potential exhaustion points
    """

    def __init__(
        self,
        wave_len: int = 10,
        wave_smooth: int = 21,
        signal_len: int = 4,
        mf_len: int = 35,
        mf_smooth: int = 6,
        ob_level: int = 60,
        os_level: int = -60,
    ):
        self.wave_len = wave_len
        self.wave_smooth = wave_smooth
        self.signal_len = signal_len
        self.mf_len = mf_len
        self.mf_smooth = mf_smooth
        self.ob_level = ob_level
        self.os_level = os_level

    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all oscillator indicators on full bar history.
        
        Adds columns:
            Wave1, Wave2, MoneyFlow, BullReversal, BearReversal,
            BullConfluence, BearConfluence
        """
        df = bars.copy()
        hlc3 = (df["High"] + df["Low"] + df["Close"]) / 3

        # ── Engine 1: WaveTrend (Hyper Wave) ──
        esa = hlc3.ewm(span=self.wave_len, adjust=False).mean()
        d = (hlc3 - esa).abs().ewm(span=self.wave_len, adjust=False).mean()

        # Avoid division by zero
        d_safe = d.replace(0, np.nan).fillna(1e-10)
        ci = (hlc3 - esa) / (0.015 * d_safe)

        wave1 = ci.ewm(span=self.wave_smooth, adjust=False).mean()
        wave2 = wave1.rolling(window=self.signal_len).mean()

        df["Wave1"] = wave1
        df["Wave2"] = wave2

        # ── Engine 2: Smart Money Flow ──
        # Money Flow Index (MFI) — manual calculation
        mfi = self._calculate_mfi(df, self.mf_len)
        # Normalize to wave scale: (MFI * 2) - 100  →  range [-100, 100]
        shifted_mf = (mfi * 2) - 100
        smooth_mf = shifted_mf.rolling(window=self.mf_smooth).mean()
        df["MoneyFlow"] = smooth_mf

        # ── Crossover / Crossunder detection ──
        cross_up = (wave1 > wave2) & (wave1.shift(1) <= wave2.shift(1))
        cross_dn = (wave1 < wave2) & (wave1.shift(1) >= wave2.shift(1))

        # ── Reversal Detection ──
        df["BullReversal"] = cross_up & (wave1 <= self.os_level)
        df["BearReversal"] = cross_dn & (wave1 >= self.ob_level)

        # ── Confluence Logic ──
        df["BullConfluence"] = (wave1 > wave2) & (smooth_mf > 0)
        df["BearConfluence"] = (wave1 < wave2) & (smooth_mf < 0)

        # ── Zone flags ──
        df["Overbought"] = wave1 >= self.ob_level
        df["Oversold"] = wave1 <= self.os_level

        return df

    def evaluate_bar(self, bars: pd.DataFrame) -> OscillatorState:
        """
        Evaluate oscillator state for the LAST bar.
        Returns a structured OscillatorState for signal filtering.
        """
        df = self.compute(bars)
        idx = len(df) - 1

        w1 = df["Wave1"].iloc[idx]
        w2 = df["Wave2"].iloc[idx]
        mf = df["MoneyFlow"].iloc[idx] if not np.isnan(df["MoneyFlow"].iloc[idx]) else 0.0

        bull_conf = df["BullConfluence"].iloc[idx]
        bear_conf = df["BearConfluence"].iloc[idx]

        # Confluence strength: normalized agreement between wave and money flow
        if bull_conf:
            strength = min(abs(w1 - w2) / 20.0, 1.0)
        elif bear_conf:
            strength = -min(abs(w1 - w2) / 20.0, 1.0)
        else:
            strength = 0.0

        return OscillatorState(
            wave1=w1,
            wave2=w2,
            money_flow=mf,
            is_overbought=w1 >= self.ob_level,
            is_oversold=w1 <= self.os_level,
            bull_reversal=bool(df["BullReversal"].iloc[idx]),
            bear_reversal=bool(df["BearReversal"].iloc[idx]),
            bull_confluence=bool(bull_conf),
            bear_confluence=bool(bear_conf),
            confluence_strength=strength,
        )

    @staticmethod
    def _calculate_mfi(df: pd.DataFrame, period: int) -> pd.Series:
        """
        Money Flow Index (MFI) calculation.
        Replicates ta.mfi(hlc3, period) from Pine Script.
        """
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        raw_money_flow = typical_price * df["Volume"]

        # Direction
        positive_flow = pd.Series(0.0, index=df.index)
        negative_flow = pd.Series(0.0, index=df.index)

        tp_diff = typical_price.diff()
        positive_flow[tp_diff > 0] = raw_money_flow[tp_diff > 0]
        negative_flow[tp_diff < 0] = raw_money_flow[tp_diff < 0]

        positive_sum = positive_flow.rolling(window=period).sum()
        negative_sum = negative_flow.rolling(window=period).sum()

        # Avoid division by zero
        money_ratio = positive_sum / negative_sum.replace(0, np.nan).fillna(1e-10)
        mfi = 100 - (100 / (1 + money_ratio))

        return mfi
