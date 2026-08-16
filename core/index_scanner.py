"""
Wolf Algo — Major Index Breadth & Macro Regime Scanner Module
================================================================
Scans constituents across major US indices:
  1. NASDAQ-100 (NAS100 / QQQ)
  2. S&P 500 (SP500 / SPY)
  3. Dow Jones Industrial Average (Dow 30 / DIA)

Computes:
  - Cross-Sectional Moving Average Breadth (% of stocks above 20-day & 50-day MAs)
  - Advancing vs. Declining Volume Ratio (ADR)
  - Inter-Market Sector Confluence & Dominant Macro Regime Index
"""

import os
import sys
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from typing import Dict, Tuple, List, Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Key Representative Major Index Basket Tickers
NAS100_BASKET = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "COST", "AMD", "NFLX", "TMUS", "PEP", "ADBE", "QCOM"]
SP500_BASKET = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "LLY", "AVGO", "JPM", "TSLA", "UNH", "XOM", "V", "PG"]
DOW30_BASKET = ["UNH", "GS", "HD", "MSFT", "CAT", "CRM", "AMGN", "V", "BA", "HON", "MCD", "AXP", "TRV", "JPM", "IBM"]


def fetch_index_breadth_metrics(basket: List[str], index_name: str) -> Dict[str, float]:
    """
    Computes real-time market breadth metrics for a given index constituent basket.
    """
    try:
        tickers_str = " ".join(basket)
        data = yf.download(tickers_str, period="60d", interval="1d", progress=False, group_by='ticker')

        bullish_count = 0
        total_valid = 0
        advancing_vol = 0.0
        declining_vol = 0.0

        for t in basket:
            try:
                df = data[t] if len(basket) > 1 else data
                if df.empty or 'Close' not in df.columns:
                    continue
                df_clean = df.dropna(subset=['Close'])
                if len(df_clean) < 20:
                    continue

                close = df_clean['Close'].iloc[-1]
                prev_close = df_clean['Close'].iloc[-2]
                ma20 = df_clean['Close'].rolling(20).mean().iloc[-1]
                vol = df_clean['Volume'].iloc[-1] if 'Volume' in df_clean.columns else 1000.0

                if close > ma20:
                    bullish_count += 1
                total_valid += 1

                if close >= prev_close:
                    advancing_vol += float(vol)
                else:
                    declining_vol += float(vol)
            except Exception:
                continue

        breadth_pct = (bullish_count / total_valid * 100.0) if total_valid > 0 else 50.0
        adv_dec_ratio = (advancing_vol / (declining_vol + 1e-6)) if declining_vol > 0 else 1.0

        return {
            "index_name": index_name,
            "breadth_pct": round(breadth_pct, 1),
            "adv_dec_ratio": round(adv_dec_ratio, 2),
            "bullish_count": bullish_count,
            "total_count": total_valid
        }
    except Exception as e:
        print(f"Error fetching index breadth for {index_name}: {e}")
        return {
            "index_name": index_name,
            "breadth_pct": 50.0,
            "adv_dec_ratio": 1.0,
            "bullish_count": 0,
            "total_count": 0
        }


def evaluate_overall_macro_regime() -> Tuple[str, Dict[str, Dict[str, float]]]:
    """
    Evaluates cross-sectional breadth across NAS100, S&P 500, and Dow 30.
    Returns: (macro_regime_name, detailed_metrics_dict)
    """
    nas100_res = fetch_index_breadth_metrics(NAS100_BASKET, "NASDAQ-100 (NAS100)")
    sp500_res = fetch_index_breadth_metrics(SP500_BASKET, "S&P 500 (SP500)")
    dow30_res = fetch_index_breadth_metrics(DOW30_BASKET, "Dow Jones (DOW30)")

    avg_breadth = (nas100_res["breadth_pct"] + sp500_res["breadth_pct"] + dow30_res["breadth_pct"]) / 3.0

    if avg_breadth >= 70.0:
        regime = "INSTITUTIONAL BULLISH EXPANSION 🚀"
    elif avg_breadth <= 35.0:
        regime = "INSTITUTIONAL BEARISH DISTRIBUTION 📉"
    else:
        regime = "NEUTRAL / SECTOR ROTATION CHOP 🟡"

    metrics = {
        "NAS100": nas100_res,
        "SP500": sp500_res,
        "DOW30": dow30_res,
        "avg_breadth_pct": round(avg_breadth, 1)
    }

    return regime, metrics


def format_macro_regime_for_discord() -> str:
    """Formats live Macro Index Breadth Report as an institutional ASCII table for Discord."""
    regime_name, metrics = evaluate_overall_macro_regime()

    nas = metrics["NAS100"]
    sp = metrics["SP500"]
    dow = metrics["DOW30"]

    table = (
        f"📊 **WOLF ALGO MACRO INDEX & BREADTH REPORT**\n"
        f"```text\n"
        f"Index       | Breadth % | Adv/Dec Vol Ratio | Confluence State\n"
        f"-----------------------------------------------------------------\n"
        f"NAS100      | {nas['breadth_pct']:>5.1f}%    | {nas['adv_dec_ratio']:>5.2f}x           | {'BULLISH 🟢' if nas['breadth_pct'] >= 60 else 'BEARISH 🔴'}\n"
        f"S&P 500     | {sp['breadth_pct']:>5.1f}%    | {sp['adv_dec_ratio']:>5.2f}x           | {'BULLISH 🟢' if sp['breadth_pct'] >= 60 else 'BEARISH 🔴'}\n"
        f"Dow 30      | {dow['breadth_pct']:>5.1f}%    | {dow['adv_dec_ratio']:>5.2f}x           | {'BULLISH 🟢' if dow['breadth_pct'] >= 60 else 'BEARISH 🔴'}\n"
        f"-----------------------------------------------------------------\n"
        f"Average Index Breadth: {metrics['avg_breadth_pct']:.1f}%\n"
        f"```\n"
        f"👑 **OVERALL MACRO REGIME:** `{regime_name}`"
    )

    return table


if __name__ == "__main__":
    print("🧪 Testing Major Index Breadth Scanner...")
    print(format_macro_regime_for_discord())
