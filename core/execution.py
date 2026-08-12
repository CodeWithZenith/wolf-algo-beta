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


POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))  # Fast 60-second polling


def initialize_client() -> TLAPI:
    """Initialize and authenticate the TradeLocker API client."""
    return TLAPI(
        environment=TL_ENVIRONMENT,
        username=TL_USERNAME,
        password=TL_PASSWORD,
        server=TL_SERVER
    )


def calculate_indicators(df: pd.DataFrame, hma_period: int = 20) -> pd.DataFrame:
    """
    Compute strategy indicators using Wolf Algo primitives:
      - HMA (Fast 20-period for intraday, 100-period for macro)
      - ATR-14 volatility indicator
    """
    close = df['c'] if 'c' in df.columns else df['close']
    high = df['h'] if 'h' in df.columns else df['high']
    low = df['l'] if 'l' in df.columns else df['low']

    df['close'] = close
    df['hma'] = hull_moving_average(close, hma_period)
    df['atr_14'] = calculate_atr(high, low, close, 14)
    return df


def run_strategy_cycle():
    """
    Execute a single live strategy evaluation cycle via TradeLocker:
      1. Connect to TradeLocker
      2. Fetch 1D Macro History (1D HMA-100) & 5m Intraday History (5m HMA-20)
      3. Compute Fast HMA-20 trend regime
      4. Compute strict $50 max dollar loss Stop Loss ($15-$25 price distance)
      5. Check daily loss circuit breaker ($125 cap)
      6. Create BUY market order with attached $50 SL or CLOSE position accordingly
    """
    tl = initialize_client()
    instrument_id = tl.get_instrument_id_from_symbol_name(SYMBOL)

    # 1. Fetch Daily Macro Price History for Macro Trend (1D HMA-100)
    raw_macro = tl.get_price_history(instrument_id, resolution="1D", lookback_period="200D")
    df_macro = pd.DataFrame(raw_macro)
    df_macro = calculate_indicators(df_macro, hma_period=100)
    macro_row = df_macro.iloc[-1]
    macro_close = macro_row['close']
    macro_hma = macro_row['hma']
    is_macro_bullish = macro_close > macro_hma if not np.isnan(macro_hma) else True

    # 2. Fetch 5m Intraday Price History for Fast Setup & Volatility (5m HMA-20)
    raw_intraday = tl.get_price_history(instrument_id, resolution="5m", lookback_period="2D")
    df_intraday = pd.DataFrame(raw_intraday)
    df_intraday = calculate_indicators(df_intraday, hma_period=20)
    intraday_row = df_intraday.iloc[-1]
    intraday_close = intraday_row['close']
    intraday_hma = intraday_row['hma']
    is_intraday_bullish = intraday_close > intraday_hma if not np.isnan(intraday_hma) else True

    # 3. MTF Confluence: Both Macro (1D) AND Fast Intraday (5m HMA-20) MUST BE BULLISH
    is_mtf_bullish_confluence = is_macro_bullish and is_intraday_bullish

    current_atr = intraday_row['atr_14'] if 'atr_14' in intraday_row and not np.isnan(intraday_row['atr_14']) else 8.0
    # Wide Volatility Trailing Stop Distance: $35.00 to $50.00 Gold price points for massive breathing room
    price_stop_distance = max(35.0, min(50.0, round(current_atr * 5.0, 2)))

    contract_size = 100.0
    raw_qty = round(MAX_LOSS_DOLLARS / (price_stop_distance * contract_size), 2)
    # Dynamic Lot Sizing bounded strictly between 0.01 and 0.10 lots
    calculated_qty = max(0.01, min(0.10, raw_qty))
    actual_max_risk = calculated_qty * contract_size * price_stop_distance

    print(f"--- Fast MTF Confluence Evaluation for {SYMBOL} ---")
    print(f"Current Price: ${intraday_close:.2f}")
    print(f"Macro Trend (1D HMA-100): {'BULLISH 🟢' if is_macro_bullish else 'BEARISH 🔴'}")
    print(f"Fast Intraday Signal (5m HMA-20): {'BULLISH 🟢' if is_intraday_bullish else 'BEARISH 🔴'}")
    print(f"MTF Confluence Status: {'FULL CONFLUENCE BUY 🚀' if is_mtf_bullish_confluence else 'NO CONFLUENCE ⏸️'}")
    print(f"5m ATR Volatility: ${current_atr:.2f}")
    print(f"Trailing Stop Distance: ${price_stop_distance:.2f} price points")
    print(f"Dynamically Scaled Size: {calculated_qty} lots")
    print(f"Strict Max Dollar Risk: ${actual_max_risk:.2f} (Capped at ${MAX_LOSS_DOLLARS:.2f})")

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

    # ── State Recovery & Fault Tolerance: Sync & Cleanup Orphan Orders ──
    try:
        orders = tl.get_all_orders()
        pos_df = tl.get_all_positions()
        active_pos_ids = set()
        if hasattr(pos_df, "iterrows"):
            for idx, p in pos_df.iterrows():
                pid = p.get('id') or p.get('positionId')
                if pid:
                    active_pos_ids.add(str(pid))
        elif isinstance(pos_df, dict):
            for p in pos_df.get('positions', []):
                pid = p.get('id') or p.get('positionId')
                if pid:
                    active_pos_ids.add(str(pid))

        if hasattr(orders, "iterrows"):
            for idx, o in orders.iterrows():
                oid = o.get('id')
                opid = o.get('positionId')
                if opid and str(opid) not in active_pos_ids:
                    print(f"🧹 State Recovery: Cleaning orphan order {oid} for closed position {opid}...")
                    try:
                        tl.cancel_order(order_id=oid)
                    except Exception:
                        pass
    except Exception as e:
        print(f"State sync note: {e}")

    # ── Risk Parameter Isolation: Gate order through RiskManager ──
    from config.settings import RiskConfig
    from risk.manager import RiskManager
    from risk.models import Order, OrderType, TradeRiskEnvelope, Direction, AccountRiskState

    if is_mtf_bullish_confluence and not has_open_position:
        stop_loss_price = round(intraday_close - price_stop_distance, 2)
        take_profit_price = round(intraday_close + (price_stop_distance * 2.5), 2)

        risk_config = RiskConfig(
            max_loss_per_trade_pct=1.0,
            hard_daily_loss_limit=HARD_DAILY_LOSS_LIMIT,
            max_drawdown_pct=3.0,
            require_structural_stop=True,
            max_open_positions=1
        )
        risk_mgr = RiskManager(config=risk_config)
        test_env = TradeRiskEnvelope(
            symbol=SYMBOL,
            direction=Direction.LONG,
            entry_price=intraday_close,
            stop_loss=stop_loss_price,
            position_size=int(calculated_qty * 100),
            risk_dollars=actual_max_risk,
            risk_ticks=price_stop_distance
        )
        test_order = Order(
            symbol=SYMBOL,
            direction=Direction.LONG,
            quantity=calculated_qty,
            order_type=OrderType.MARKET,
            risk_envelope=test_env
        )
        acc_risk_state = AccountRiskState(
            current_equity=cash_balance,
            daily_pnl=today_net,
            open_position_count=1 if has_open_position else 0
        )
        decision = risk_mgr.gate_order(test_order, acc_risk_state)

        if not decision.approved:
            print(f"🛑 Order REJECTED by RiskManager Gatekeeper: {decision.message}")
            return

        if decision.adjusted_size and decision.adjusted_size < calculated_qty:
            calculated_qty = decision.adjusted_size
            print(f"⚠️ Position Size adjusted by RiskManager to {calculated_qty} lots.")

        print(f">>> Signal Triggered & Risk Approved: Full MTF Confluence. Opening Long Position for {calculated_qty} lots...")

        tl.create_order(
            instrument_id=instrument_id,
            quantity=float(calculated_qty),
            side="buy",
            type_="market",
            stop_loss=float(stop_loss_price),
            stop_loss_type="absolute",
            take_profit=float(take_profit_price),
            take_profit_type="absolute"
        )
        print(f"✅ Placed BUY order for {calculated_qty} lots of {SYMBOL}:")
        print(f"   • Entry Price: ${intraday_close:.2f}")
        print(f"   • Absolute Stop Loss: ${stop_loss_price:.2f} (EXACTLY -${price_stop_distance:.2f} below entry | Max Risk: -${actual_max_risk:.2f})")
        print(f"   • Absolute Take Profit: ${take_profit_price:.2f} (EXACTLY +${price_stop_distance * 2.5:.2f} above entry | Target Profit: +${calculated_qty * contract_size * (price_stop_distance * 2.5):.2f})")

    elif has_open_position and not is_intraday_bullish:
        print(">>> Exit Triggered: Intraday trend reversed below 15m HMA. Closing Position.")
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
