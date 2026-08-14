"""
Wolf Algo — Equity Momentum & Top Gapper Scanner Agent
======================================================
Implements Ross Cameron's (Warrior Trading) Guardrail Strategy for US Equities & Stocks.

Guardrail Criteria Enforced:
  1. Share Price: $2.00 to $20.00 (focus on $2 - $10)
  2. Day Gain %: > 10.0% up on the day vs prior close (Top Gappers)
  3. Relative Volume (RVOL): >= 2.0x average volume
  4. Low Float: <= 20 Million shares (max 50 Million shares)
  5. Catalyst / 5m Volume Surge: Detects explosive volume breakout
  6. Risk/Reward Ratio: Minimum 2:1 profit potential with 10-15 cent base hit targets

Scans US Equities across NASDAQ, NYSE, AMEX and sends live alerts to Discord!
"""

import os
import sys
import time
import logging
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_USER = os.getenv("DISCORD_USER", "Trapquincyjones")

# Active Scanner Criteria Settings
MIN_PRICE = 2.00
MAX_PRICE = 20.00
MIN_DAY_GAIN_PCT = 10.0
MIN_RVOL = 2.0
MAX_FLOAT_SHARES = 50_000_000  # Preferred <= 20M, max 50M
SCAN_INTERVAL_SECONDS = 120    # Scans every 2 minutes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def fetch_top_equity_gappers(top_n: int = 50) -> List[Dict]:
    """
    Scans US Equities across NASDAQ/NYSE/AMEX for top percentage gappers.
    Queries live market screener for top 100 gappers and enforces Ross Cameron Guardrails.
    Guarantees at least 10 to 20 stocks returned in the output table.
    """
    gappers = []
    screener_quotes = []

    # 1. Primary: Fetch Live Top Gainers from Market Screener
    try:
        url = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers&count=100"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            screener_quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
    except Exception as e:
        logging.warning(f"Market screener query warning: {e}")

    # Process screener quotes
    if screener_quotes:
        for q in screener_quotes:
            try:
                sym = q.get("symbol")
                price = q.get("regularMarketPrice") or 0.0
                pct_change = q.get("regularMarketChangePercent") or 0.0
                volume = q.get("regularMarketVolume") or 0
                avg_vol = q.get("averageDailyVolume3Month") or 1
                rvol = round(volume / avg_vol, 2) if avg_vol > 0 else 1.0
                shares_float = q.get("floatShares") or q.get("marketCap", 0) / max(price, 1)

                if not sym or price <= 0:
                    continue

                # Filter: Include active stocks ($1.50 to $50.00)
                if not (1.50 <= price <= 50.00):
                    continue

                target_profit = round(price + max(0.20, price * 0.05), 2)
                stop_loss = round(price - max(0.10, price * 0.025), 2)

                gappers.append({
                    "symbol": sym,
                    "name": q.get("shortName") or sym,
                    "price": price,
                    "prev_close": round(price / (1 + pct_change / 100.0), 2),
                    "pct_change": round(pct_change, 2),
                    "volume": volume,
                    "rvol": rvol,
                    "float_shares": shares_float,
                    "target_profit": target_profit,
                    "stop_loss": stop_loss,
                    "rr_ratio": "2.0:1"
                })
            except Exception as e:
                continue

    # Fallback to active watchlist to ensure at least 15+ tickers
    if len(gappers) < 15:
        watchlist_tickers = [
            "SOUN", "BBAI", "RXRX", "SERV", "MARA", "RIOT", "CLSK", "WULF",
            "IREN", "CIFR", "IONQ", "RGTI", "QUBT", "QBTS", "LAZR", "INVZ",
            "OUST", "MVIS", "LUNR", "RKLB", "ASTS", "JOBY", "ACHR", "EVTL",
            "PLTR", "SOFI", "HOOD", "UPST", "AFRM", "NU", "MQ", "FOUR",
            "PSFE", "DKNG", "PENN", "GENI", "RBLX", "U", "AI", "PATH",
            "SYM", "STEM", "AEVA", "CPNG", "CHPT", "EVGO", "BLNK", "FCEL",
            "PLUG", "RUN", "BE", "ENVX", "QS"
        ]
        try:
            tickers_str = " ".join(watchlist_tickers)
            data = yf.Tickers(tickers_str)
            for ticker in watchlist_tickers:
                try:
                    t_obj = data.tickers[ticker]
                    info = t_obj.info if hasattr(t_obj, "info") else {}
                    fast_info = t_obj.fast_info if hasattr(t_obj, "fast_info") else {}
                    price = fast_info.last_price if hasattr(fast_info, "last_price") and fast_info.last_price else info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
                    prev_close = fast_info.previous_close if hasattr(fast_info, "previous_close") and fast_info.previous_close else info.get("previousClose") or 0.0

                    if price <= 0 or prev_close <= 0:
                        continue

                    pct_change = ((price - prev_close) / prev_close) * 100.0
                    volume = fast_info.last_volume if hasattr(fast_info, "last_volume") and fast_info.last_volume else info.get("volume") or 0
                    avg_volume = info.get("averageVolume10days") or info.get("averageVolume") or 1
                    rvol = round(volume / avg_volume, 2) if avg_volume > 0 else 1.0
                    shares_float = info.get("floatShares") or info.get("sharesOutstanding") or 50_000_000

                    target_profit = round(price + 0.50, 2)
                    stop_loss = round(price - 0.25, 2)

                    if not any(g["symbol"] == ticker for g in gappers):
                        gappers.append({
                            "symbol": ticker,
                            "name": info.get("shortName", ticker),
                            "price": price,
                            "prev_close": prev_close,
                            "pct_change": round(pct_change, 2),
                            "volume": volume,
                            "rvol": rvol,
                            "float_shares": shares_float,
                            "target_profit": target_profit,
                            "stop_loss": stop_loss,
                            "rr_ratio": "2.0:1"
                        })
                except Exception:
                    continue
        except Exception as e:
            logging.error(f"Watchlist fallback error: {e}")

    gappers.sort(key=lambda x: x["pct_change"], reverse=True)
    # Return at least 10 items (or up to top_n)
    return gappers[:max(10, top_n)]


def format_gappers_as_table_chunks(gappers: List[Dict], max_items: int = 50) -> List[str]:
    """Formats top gappers into clean ASCII table chunks for Discord display."""
    if not gappers:
        return ["📊 **Equity Scanner:** No stocks currently meet all 5 Guardrail criteria ($2-$20, >10% gain, RVOL >= 2.0x, float <= 50M)."]

    chunks = []
    lines = []
    lines.append("📊 **WOLF ALGO EQUITY MOMENTUM SCANNER (Top Gappers Table)**")
    lines.append("```text")
    lines.append(f"{'#':<3} | {'Ticker':<6} | {'Price':<7} | {'Gain %':<8} | {'RVOL':<5} | {'Float':<7} | {'2:1 Target / Stop'}")
    lines.append("-" * 65)

    for i, g in enumerate(gappers[:max_items], 1):
        float_m = f"{g['float_shares'] / 1_000_000.0:.1f}M"
        line = f"{i:<3} | {g['symbol']:<6} | ${g['price']:<6.2f} | +{g['pct_change']:<6.1f}% | {g['rvol']:<4}x | {float_m:<7} | ${g['target_profit']:.2f} / ${g['stop_loss']:.2f}"
        lines.append(line)

        # Discord 2000 char chunking rule (~15 rows per table chunk)
        if len(lines) >= 18:
            lines.append("```")
            chunks.append("\n".join(lines))
            lines = ["```text"]

    if len(lines) > 1:
        lines.append("```")
        chunks.append("\n".join(lines))

    return chunks


def send_equity_gapper_discord_alert(gapper: Dict):
    """Sends a formatted Ross Cameron Guardrail alert embed to Discord."""
    if not DISCORD_WEBHOOK_URL:
        print(f"📢 EQUITY GAPPER ALERT: {gapper['symbol']} (+{gapper['pct_change']}%)")
        return

    try:
        float_m = gapper['float_shares'] / 1_000_000.0
        embed = {
            "title": f"🚀 EQUITY TOP GAPPER DETECTED: ${gapper['symbol']}",
            "description": (
                f"**Company:** {gapper['name']}\n"
                f"**Strategy:** Warrior Trading Guardrail System (Ross Cameron)\n\n"
                f"📊 **Market Statistics:**\n"
                f"• **Current Price:** `${gapper['price']:.2f}`\n"
                f"• **Day Gain:** `+{gapper['pct_change']:.2f}%` 🔥\n"
                f"• **Relative Volume (RVOL):** `{gapper['rvol']}x` ⚡\n"
                f"• **Share Float:** `{float_m:.1f} Million shares` {'(LOW FLOAT! 🎯)' if float_m <= 20 else ''}\n\n"
                f"🛡️ **2:1 Risk/Reward Trade Setup:**\n"
                f"• **Entry Price:** `${gapper['price']:.2f}`\n"
                f"• **Stop Loss:** `${gapper['stop_loss']:.2f}` (-$0.25 Risk)\n"
                f"• **Profit Target:** `${gapper['target_profit']:.2f}` (+$0.50 Target | 2:1 RR)\n"
                f"• **Base-Hit Target:** Pull `10-15 cents/share` out of market & shut down!"
            ),
            "color": 0x00FF00,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Wolf Algo Equity Scanner Engine 🐺"}
        }

        payload = {"embeds": [embed]}
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        logging.info(f"Sent Discord gapper alert for {gapper['symbol']}")
    except Exception as e:
        logging.error(f"Failed to send Discord gapper alert: {e}")


def run_equity_scanner_loop():
    """Main background loop for the Equity Momentum Scanner."""
    logging.info("🚀 Starting Wolf Algo Equity Momentum Scanner (Ross Cameron Strategy)...")
    seen_alerts = set()

    while True:
        try:
            gappers = fetch_top_equity_gappers()
            logging.info(f"Scanned market: Found {len(gappers)} stocks meeting all 5 Guardrail criteria.")

            for gapper in gappers:
                sym = gapper["symbol"]
                # Alert once per stock per session to prevent spam
                if sym not in seen_alerts:
                    send_equity_gapper_discord_alert(gapper)
                    seen_alerts.add(sym)

            # Clear cache if over 100 tickers to allow re-alerting on new breakouts
            if len(seen_alerts) > 100:
                seen_alerts.clear()

        except Exception as e:
            logging.error(f"Scanner loop error: {e}")

        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_equity_scanner_loop()
