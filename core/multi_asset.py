"""
Wolf Algo — Multi-Asset Instrument Resolution & Trading Engine
================================================================
Expands execution capabilities across multiple asset classes:
  1. Gold (XAUUSD / XAUUSD.R)
  2. US30 / Dow Jones Futures (US30 / DJ30 / WS30)
  3. NAS100 / Nasdaq-100 Futures (NAS100 / US100 / NDX)
  4. EURUSD / Major Forex (EURUSD)
  5. BTCUSD / Crypto (BTCUSD / BTCUSDT)
"""

import os
import sys
import pandas as pd
from typing import Dict, Optional, Tuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Supported Instrument Map Across Brokers & Symbols
SUPPORTED_ASSET_MAP = {
    "XAUUSD": {"name": "Gold Spot", "default_symbol": "XAUUSD.R", "yahoo_symbol": "GC=F", "pip_scale": 1.0, "sl_dist_100k": 5.00, "sl_dist_1k": 1.00},
    "US30": {"name": "Dow Jones 30 Futures", "default_symbol": "US30.R", "yahoo_symbol": "^DJI", "pip_scale": 1.0, "sl_dist_100k": 50.00, "sl_dist_1k": 15.00},
    "NAS100": {"name": "Nasdaq-100 Futures", "default_symbol": "NAS100.R", "yahoo_symbol": "^NDX", "pip_scale": 1.0, "sl_dist_100k": 25.00, "sl_dist_1k": 10.00},
    "EURUSD": {"name": "Euro / US Dollar", "default_symbol": "EURUSD.R", "yahoo_symbol": "EURUSD=X", "pip_scale": 0.0001, "sl_dist_100k": 0.0020, "sl_dist_1k": 0.0010},
    "BTCUSD": {"name": "Bitcoin / US Dollar", "default_symbol": "BTCUSD.R", "yahoo_symbol": "BTC-USD", "pip_scale": 1.0, "sl_dist_100k": 500.00, "sl_dist_1k": 150.00}
}


def normalize_asset_key(raw_input: str) -> str:
    """Normalizes user input to standard asset key (e.g. '!quant us30' -> 'US30')."""
    inp = raw_input.strip().upper()
    if any(k in inp for k in ["US30", "DJ30", "WS30", "DOW", "DOW30"]):
        return "US30"
    elif any(k in inp for k in ["NAS100", "US100", "NDX", "NASDAQ"]):
        return "NAS100"
    elif any(k in inp for k in ["EURUSD", "EUR/USD", "EUR"]):
        return "EURUSD"
    elif any(k in inp for k in ["BTCUSD", "BTC", "BITCOIN", "BTCUSDT"]):
        return "BTCUSD"
    elif any(k in inp for k in ["GOLD", "XAUUSD", "XAUUSD.R", "XAU"]):
        return "XAUUSD"
    return "XAUUSD"


def get_asset_parameters(asset_key: str, account_balance: float = 100000.0) -> Dict:
    """Returns lot sizing, SL distance, and broker configuration for a given asset."""
    key = normalize_asset_key(asset_key)
    config = SUPPORTED_ASSET_MAP[key].copy()

    if account_balance >= 50000.0:
        qty = 0.10
        sl_dist = config["sl_dist_100k"]
        max_risk = 50.00
    else:
        qty = 0.05
        sl_dist = config["sl_dist_1k"]
        max_risk = 5.00

    config["qty"] = qty
    config["sl_dist"] = sl_dist
    config["max_risk"] = max_risk

    return config


if __name__ == "__main__":
    print("🧪 Testing Multi-Asset Parameters...")
    for a in ["XAUUSD", "US30", "NAS100", "EURUSD", "BTCUSD"]:
        p = get_asset_parameters(a, 100000.0)
        print(f"Asset {a}: Qty={p['qty']} | SL Dist={p['sl_dist']} | Max Risk=${p['max_risk']}")
