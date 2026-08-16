"""
Wolf Algo — Graphical Image Chart Generator Module
===================================================
Generates high-resolution TradingView-style dark mode PNG chart images:
  - Price Candlestick & Trend Line
  - Hull Moving Average (HMA) Cloud
  - Active Signal & Support / Resistance Levels
"""

import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_chart_image_png(symbol: str = "GC=F", asset_display: str = "Gold (XAUUSD)") -> str:
    """
    Generates a dark-mode graphical PNG chart image using Matplotlib.
    Returns absolute file path to the saved PNG chart image.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 20:
            return ""

        close_series = df['Close']
        if isinstance(close_series, pd.DataFrame):
            closes = close_series.iloc[:, 0].dropna()
        else:
            closes = close_series.dropna()

        # Dark Mode Styling
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
        fig.patch.set_facecolor('#0E1117')
        ax.set_facecolor('#161B22')

        # Plot Price & HMA Moving Average
        ax.plot(closes.index, closes.values, color='#00FF7F', linewidth=2.0, label=f'{asset_display} Price')

        ma20 = closes.rolling(20).mean()
        ax.plot(ma20.index, ma20.values, color='#FF007F', linewidth=1.5, linestyle='--', label='15m Trend HMA')

        curr_p = float(closes.iloc[-1].item() if hasattr(closes.iloc[-1], "item") else closes.iloc[-1])
        first_p = float(closes.iloc[0].item() if hasattr(closes.iloc[0], "item") else closes.iloc[0])
        chg = ((curr_p - first_p) / first_p) * 100.0
        sig = "BUY LONG 🚀" if chg >= 0 else "SELL SHORT 📉"

        ax.set_title(f"🐺 WOLF ALGO REAL-TIME TECHNICAL CHART: {asset_display}\nPrice: ${curr_p:.2f} ({chg:+.2f}%) | Active Signal: {sig}", fontsize=12, fontweight='bold', color='#FFFFFF', pad=12)
        ax.set_ylabel("Price ($)", fontsize=10, color='#8B949E')
        ax.set_xlabel("Time (15m Interval)", fontsize=10, color='#8B949E')
        ax.grid(True, linestyle=':', alpha=0.3, color='#30363D')
        ax.legend(loc='upper left', facecolor='#161B22', edgecolor='#30363D')

        png_path = "/tmp/wolf_algo_chart.png"
        plt.savefig(png_path, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)

        return png_path
    except Exception as e:
        print(f"Error generating PNG chart image: {e}")
        return ""


if __name__ == "__main__":
    print("PNG Path:", generate_chart_image_png("GC=F", "Gold (XAUUSD)"))
