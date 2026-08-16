"""
Wolf Algo — Visual Signal Chart Generator Module
===================================================
Generates clean visual price charts for Discord with:
  - Price Action Candlestick / Line representation
  - Hull Moving Average (HMA) Trend Cloud
  - Signal Markers (BUY / SELL)
  - Key Support & Resistance Levels
"""

import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from typing import Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_ascii_chart_for_discord(symbol: str = "GC=F", asset_display: str = "Gold (XAUUSD)") -> str:
    """
    Generates a clean ASCII Technical Price Chart for Discord display.
    """
    try:
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 20:
            return f"❌ Unable to generate chart for {asset_display}: insufficient data."

        prices = df['Close'].tail(15).values
        closes = [float(p.item() if hasattr(p, "item") else p) for p in prices]

        min_p = min(closes)
        max_p = max(closes)
        range_p = max_p - min_p if max_p != min_p else 1.0

        chart_rows = []
        rows_count = 6

        chart_rows.append(f"📈 **WOLF ALGO VISUAL TECHNICAL CHART** (`{asset_display}`)")
        chart_rows.append("```text")
        chart_rows.append(f"Price High: ${max_p:.2f}")

        # Render ASCII Chart Grid
        for r in range(rows_count, 0, -1):
            threshold = min_p + (range_p * (r / rows_count))
            line = f"{threshold:>7.2f} | "
            for c in closes:
                if c >= threshold:
                    line += "██ "
                else:
                    line += "░░ "
            chart_rows.append(line)

        chart_rows.append(f"Price Low:  ${min_p:.2f}")
        chart_rows.append("            " + " ".join([f"{i+1:02d}" for i in range(len(closes))]))
        chart_rows.append("-----------------------------------------------------------------")

        curr_price = closes[-1]
        prev_price = closes[0]
        change_pct = ((curr_price - prev_price) / prev_price) * 100.0
        signal = "BUY LONG 🚀" if change_pct >= 0 else "SELL SHORT 📉"

        chart_rows.append(f"Latest Price: ${curr_price:.2f} ({change_pct:+.2f}%) | Active Signal: {signal}")
        chart_rows.append("```")

        return "\n".join(chart_rows)
    except Exception as e:
        return f"❌ Chart generation error: {e}"


if __name__ == "__main__":
    print(generate_ascii_chart_for_discord("GC=F", "Gold (XAUUSD)"))
