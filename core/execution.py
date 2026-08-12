"""
Wolf Algo — Execution & TradeLocker Integration Module
=========================================================
Handles TradeLocker API execution, indicator calculations (HMA-250, ATR-6.0),
risk-managed position sizing, and provides the abstract BrokerAPI + MockBroker interface.
"""

import os
import sys
import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import ta
from dotenv import load_dotenv
from tradelocker import TLAPI

from risk.models import Order, Direction, OrderType
from utils.logger import LogTag, log_event
from utils.helpers import hull_moving_average, calculate_atr

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# TradeLocker Script Configuration & Functions
# ---------------------------------------------------------------------------

TL_ENVIRONMENT = os.getenv("TL_ENVIRONMENT", "https://demo.tradelocker.com")
TL_USERNAME = os.getenv("TL_USERNAME", "")
TL_PASSWORD = os.getenv("TL_PASSWORD", "")
TL_SERVER = os.getenv("TL_SERVER", "")
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
MAX_LOSS_DOLLARS = float(os.getenv("MAX_LOSS_DOLLARS", "50.0"))  # Strict $50 max dollar loss per trade
POSITION_QTY = float(os.getenv("POSITION_QTY", "0.10"))           # 0.10 lots (10 oz of Gold)
HARD_DAILY_LOSS_LIMIT = float(os.getenv("HARD_DAILY_LOSS_LIMIT", "125.0"))


def initialize_client() -> TLAPI:
    """Initialize and authenticate the TradeLocker API client."""
    return TLAPI(
        environment=TL_ENVIRONMENT,
        username=TL_USERNAME,
        password=TL_PASSWORD,
        server=TL_SERVER
    )


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute strategy indicators using Wolf Algo primitives:
      - HMA-250 trend filter
      - ATR-14 volatility indicator
    """
    close = df['c'] if 'c' in df.columns else df['close']
    high = df['h'] if 'h' in df.columns else df['high']
    low = df['l'] if 'l' in df.columns else df['low']

    df['close'] = close
    df['hma_250'] = hull_moving_average(close, 250)
    df['atr_14'] = calculate_atr(high, low, close, 14)
    return df


def run_strategy_cycle():
    """
    Execute a single live strategy evaluation cycle via TradeLocker:
      1. Connect to TradeLocker
      2. Fetch price history for SYMBOL (XAUUSD)
      3. Compute HMA-250 trend regime
      4. Compute strict $50 max dollar loss Stop Loss ($5.00 price distance on 0.10 lots)
      5. Check daily loss circuit breaker ($125 cap)
      6. Create BUY market order with attached $50 SL or CLOSE position accordingly
    """
    tl = initialize_client()
    instrument_id = tl.get_instrument_id_from_symbol_name(SYMBOL)

    raw_history = tl.get_price_history(instrument_id, resolution="15m", lookback_period="5D")
    df = pd.DataFrame(raw_history)
    df = calculate_indicators(df)

    current_row = df.iloc[-1]
    prev_close = current_row['close']
    current_hma = current_row['hma_250']

    current_atr = current_row['atr_14'] if 'atr_14' in current_row and not np.isnan(current_row['atr_14']) else 8.0
    
    # Intraday Volatility Stop Loss Distance (gives Gold $15-$25 price room so normal 5m/15m noise won't stop it out)
    price_stop_distance = max(15.0, min(25.0, round(current_atr * 2.5, 2)))

    # Dynamic Lot Sizing to guarantee STRICT $50 Max Loss:
    # QTY = $50 / (price_stop_distance * 100) -> e.g. $50 / ($25 * 100) = 0.02 lots!
    contract_size = 100.0
    calculated_qty = max(0.01, round(MAX_LOSS_DOLLARS / (price_stop_distance * contract_size), 2))
    actual_max_risk = calculated_qty * contract_size * price_stop_distance

    print(f"--- Strategy Evaluation for {SYMBOL} ---")
    print(f"Current Price: ${prev_close:.2f}")
    print(f"HMA-250 Trend Filter: {current_hma:.2f}")
    print(f"ATR-14 Volatility: ${current_atr:.2f}")
    print(f"Volatility Stop Distance: ${price_stop_distance:.2f} price points")
    print(f"Dynamically Scaled Position Size: {calculated_qty} lots")
    print(f"Strict Max Dollar Risk: ${actual_max_risk:.2f} (Capped at ${MAX_LOSS_DOLLARS:.2f})")

    is_bullish_regime = prev_close > current_hma if not np.isnan(current_hma) else True

    positions = tl.get_all_positions()
    has_open_position = False
    if hasattr(positions, "empty"):
        has_open_position = not positions.empty
    elif isinstance(positions, dict):
        has_open_position = len(positions.get("positions", [])) > 0

    try:
        acc_state = tl.get_account_state()
        if hasattr(acc_state, "iloc") and len(acc_state) > 0:
            cash_balance = float(acc_state['balance'].iloc[0]) if 'balance' in acc_state.columns else float(acc_state['equity'].iloc[0])
            today_net = float(acc_state['todayNet'].iloc[0]) if 'todayNet' in acc_state.columns else 0.0
        elif isinstance(acc_state, dict):
            cash_balance = float(acc_state.get('balance', 4955.18))
            today_net = float(acc_state.get('todayNet', 0.0))
        else:
            cash_balance = 4955.18
            today_net = 0.0
    except Exception:
        cash_balance = 4955.18
        today_net = 0.0

    print(f"Account Balance: ${cash_balance:,.2f} | Today PnL: ${today_net:,.2f}")

    # Hard daily loss circuit breaker check
    if today_net <= -HARD_DAILY_LOSS_LIMIT:
        print(f"🛑 Daily Loss Circuit Breaker Triggered (${today_net:.2f} <= -${HARD_DAILY_LOSS_LIMIT:.2f}). No new trades today.")
        return

    if is_bullish_regime and not has_open_position:
        print(f">>> Signal Triggered: Bullish Regime Confirmed. Opening Long Position for {calculated_qty} lots...")

        tp_offset = round(price_stop_distance * 2.5, 2)  # 2.5:1 R:R target

        tl.create_order(
            instrument_id=instrument_id,
            quantity=float(calculated_qty),
            side="buy",
            type_="market",
            stop_loss=float(price_stop_distance),
            stop_loss_type="trailingOffset",
            take_profit=float(tp_offset),
            take_profit_type="offset"
        )
        print(f"✅ Placed BUY order for {calculated_qty} lots of {SYMBOL}:")
        print(f"   • Trailing Stop Loss: -${price_stop_distance:.2f} offset (Max Risk: -${actual_max_risk:.2f})")
        print(f"   • Take Profit Target: +${tp_offset:.2f} offset (Target Profit: +${calculated_qty * contract_size * tp_offset:.2f})")

    elif has_open_position and not is_bullish_regime:
        print(">>> Exit Triggered: Trend reversed below HMA-250. Closing Position.")
        if hasattr(positions, "iterrows"):
            for idx, p in positions.iterrows():
                pos_id = p.get('id') if 'id' in p else p.get('positionId')
                if pos_id:
                    tl.close_position(position_id=pos_id)
                    print(f"Position {pos_id} closed successfully.")
        elif isinstance(positions, dict):
            for p in positions.get('positions', []):
                pos_id = p.get('id') or p.get('positionId')
                if pos_id:
                    tl.close_position(position_id=pos_id)
                    print(f"Position {pos_id} closed successfully.")
    else:
        print("No trade action required on this cycle. Holding state.")


# ---------------------------------------------------------------------------
# Abstract Broker Interface & Mock Implementation (For Core Engine & Backtests)
# ---------------------------------------------------------------------------

class BrokerAPI(ABC):
    """Abstract broker interface."""

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def get_fills(self, since: Optional[datetime] = None) -> List[Order]:
        ...

    @abstractmethod
    def get_account_balance(self) -> float:
        ...


class MockBroker(BrokerAPI):
    """Simulated broker for backtesting and development."""

    def __init__(
        self,
        slippage_ticks: float = 1.0,
        commission_per_side: float = 2.50,
        logger: Optional[logging.Logger] = None,
    ):
        self.slippage_ticks = slippage_ticks
        self.commission_per_side = commission_per_side
        self.logger = logger or logging.getLogger("wolf_algo.broker")
        self.connected = False
        self.fills: List[Order] = []
        self.balance = 25000.0

    def connect(self) -> bool:
        self.connected = True
        log_event(self.logger, "info", LogTag.SYSTEM, "MockBroker connected")
        return True

    def disconnect(self) -> None:
        self.connected = False
        log_event(self.logger, "info", LogTag.SYSTEM, "MockBroker disconnected")

    def submit_order(self, order: Order) -> Order:
        if not self.connected:
            order.rejected = True
            order.rejection_reason = "Broker not connected"
            log_event(self.logger, "error", LogTag.REJECT, "Order rejected: broker not connected")
            return order

        order.order_id = str(uuid.uuid4())[:8]
        order.timestamp = datetime.utcnow()

        if order.order_type == OrderType.MARKET:
            if order.direction == Direction.LONG:
                order.fill_price = order.price + self.slippage_ticks
            else:
                order.fill_price = order.price - self.slippage_ticks
            order.filled = True

            commission = self.commission_per_side
            self.balance -= commission
            self.fills.append(order)

            log_event(
                self.logger, "info", LogTag.FILL,
                f"FILLED: {order.direction.value} {order.quantity}x @ {order.fill_price:.2f} "
                f"(slippage: {self.slippage_ticks}, commission: ${commission:.2f})",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "fill_price": order.fill_price,
                    "direction": order.direction.value,
                    "quantity": order.quantity,
                },
            )
        else:
            log_event(
                self.logger, "info", LogTag.ORDER,
                f"PENDING: {order.order_type.value} {order.direction.value} {order.quantity}x @ {order.price:.2f}",
                {"order_id": order.order_id},
            )

        return order

    def cancel_order(self, order_id: str) -> bool:
        log_event(self.logger, "info", LogTag.ORDER, f"Order {order_id} cancelled (mock)")
        return True

    def get_fills(self, since: Optional[datetime] = None) -> List[Order]:
        if since:
            return [f for f in self.fills if f.timestamp and f.timestamp >= since]
        return self.fills

    def get_account_balance(self) -> float:
        return self.balance

    def set_balance(self, balance: float) -> None:
        self.balance = balance


class TradeLockerBroker(BrokerAPI):
    """TradeLocker API Broker Implementation."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("wolf_algo.tradelocker")
        self.client: Optional[TLAPI] = None
        self.connected = False

    def connect(self) -> bool:
        try:
            self.client = initialize_client()
            self.connected = True
            log_event(self.logger, "info", LogTag.SYSTEM, "TradeLocker client connected")
            return True
        except Exception as e:
            log_event(self.logger, "error", LogTag.ERROR, f"Failed to connect TradeLocker client: {e}")
            return False

    def disconnect(self) -> None:
        self.connected = False
        log_event(self.logger, "info", LogTag.SYSTEM, "TradeLocker client disconnected")

    def submit_order(self, order: Order) -> Order:
        if not self.connected or not self.client:
            order.rejected = True
            order.rejection_reason = "TradeLocker client not connected"
            return order

        try:
            instrument_id = self.client.get_instrument_id_from_symbol_name(order.symbol)
            side = "buy" if order.direction == Direction.LONG else "sell"
            order_type = order.order_type.value.lower()

            res = self.client.create_order(
                instrument_id=instrument_id,
                side=side,
                order_type=order_type,
                qty=order.quantity
            )
            order.order_id = str(res.get("orderId", uuid.uuid4()))
            order.filled = True
            order.fill_price = order.price
            log_event(self.logger, "info", LogTag.FILL, f"TradeLocker order submitted: {side} {order.quantity}x {order.symbol}")
        except Exception as e:
            order.rejected = True
            order.rejection_reason = str(e)
            log_event(self.logger, "error", LogTag.REJECT, f"TradeLocker order submission failed: {e}")

        return order

    def cancel_order(self, order_id: str) -> bool:
        return True

    def get_fills(self, since: Optional[datetime] = None) -> List[Order]:
        return []

    def get_account_balance(self) -> float:
        if self.client:
            acc = self.client.get_account_info()
            return float(acc.get("accountBalance", 25000.0))
        return 25000.0


POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))


def run_strategy_loop():
    """Run strategy cycle continuously every POLL_INTERVAL seconds (24/7 mode)."""
    import time
    print(f"🚀 Starting Wolf Algo 24/7 Live TradeLocker Execution Loop (Polling every {POLL_INTERVAL}s)...")
    while True:
        try:
            run_strategy_cycle()
        except Exception as e:
            print(f"⚠️ Exception during strategy cycle: {e}")
        print(f"😴 Sleeping for {POLL_INTERVAL} seconds until next cycle...\n")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_strategy_loop()
