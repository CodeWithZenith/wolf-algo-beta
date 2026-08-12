"""
Wolf Algo — Asynchronous Agent Loop
=====================================
Main event loop that initializes the connection, listens to market data,
evaluates strategy logic, and passes orders through the risk management
gatekeeper before hitting the broker.

State Machine:
  IDLE → LISTENING → EVALUATING → ORDERING → MONITORING → (loop)
"""

import asyncio
import signal
import logging
from datetime import datetime
from typing import Optional

from config.settings import AppConfig, load_config
from core.state import AgentState
from core.execution import MockBroker, BrokerAPI
from risk.manager import RiskManager
from risk.models import (
    AccountRiskState,
    Direction,
    Order,
    OrderType,
    Position,
    TradeRiskEnvelope,
)
from strategies.base import Strategy, Signal
from utils.logger import get_logger, LogTag, log_event


class TradingAgent:
    """
    Core trading agent.

    Orchestrates:
      1. Market data ingestion
      2. Strategy signal evaluation
      3. Risk gate enforcement
      4. Order execution
      5. Position monitoring
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        strategy: Optional[Strategy] = None,
        broker: Optional[BrokerAPI] = None,
    ):
        self.config = config or load_config()
        self.logger = get_logger(
            name="wolf_algo",
            level=self.config.logging.level,
            fmt=self.config.logging.format,
            log_file=self.config.logging.file,
        )
        self.state = AgentState(
            account=AccountRiskState(
                starting_equity=self.config.account.starting_equity,
                current_equity=self.config.account.starting_equity,
                peak_equity=self.config.account.starting_equity,
            )
        )
        self.risk_manager = RiskManager(self.config.risk, self.logger)
        self.strategy = strategy
        self.broker = broker or MockBroker(
            slippage_ticks=self.config.execution.slippage_ticks,
            commission_per_side=self.config.execution.commission_per_side,
            logger=self.logger,
        )
        self._shutdown = False

    async def run(self) -> None:
        """Main event loop."""
        self._set_status("LISTENING")
        log_event(
            self.logger, "info", LogTag.SYSTEM,
            "Wolf Algo Agent starting...",
            {
                "equity": self.config.account.starting_equity,
                "strategy": self.strategy.__class__.__name__ if self.strategy else "None",
                "broker": self.broker.__class__.__name__,
            },
        )

        # Connect to broker
        if not self.broker.connect():
            log_event(self.logger, "error", LogTag.ERROR, "Failed to connect to broker. Shutting down.")
            return

        # Install signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_shutdown)

        log_event(self.logger, "info", LogTag.SYSTEM, "Agent ready. Entering main loop.")

        try:
            while not self._shutdown:
                await self._tick()
                await asyncio.sleep(0.1)  # Tick rate — adjust for live vs backtest
        except Exception as e:
            log_event(
                self.logger, "error", LogTag.ERROR,
                f"Unhandled exception in main loop: {e}",
            )
            raise
        finally:
            await self._cleanup()

    async def _tick(self) -> None:
        """Single iteration of the event loop."""
        # In live mode, this would consume a market data tick.
        # For backtest integration, the BacktestEngine drives ticks externally.
        pass

    def evaluate_and_execute(self, signal: Signal, bar_time: Optional[datetime] = None) -> None:
        """
        Process a strategy signal through the full pipeline:
        signal → risk gate → execution → position tracking.

        This is the synchronous entry point used by the backtest engine.
        """
        if signal.direction == Direction.FLAT:
            return

        self._set_status("EVALUATING")

        # Build risk envelope from signal
        envelope = TradeRiskEnvelope(
            direction=signal.direction,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_price,
            tp_levels=signal.tp_levels,
            position_size=signal.position_size or 1,
            symbol=signal.symbol,
            timestamp=bar_time,
        )

        # Build order
        order = Order(
            symbol=signal.symbol,
            direction=signal.direction,
            order_type=OrderType.MARKET,
            quantity=envelope.position_size,
            price=signal.entry_price,
            risk_envelope=envelope,
        )

        # ── Risk Gate ──
        self._set_status("ORDERING")
        decision = self.risk_manager.gate_order(order, self.state.account)

        if not decision.approved:
            log_event(
                self.logger, "warning", LogTag.REJECT,
                f"Signal rejected by risk manager: {decision.message}",
            )
            return

        # Apply adjusted size if risk manager reduced it
        if decision.adjusted_size is not None:
            order.quantity = decision.adjusted_size
            envelope.position_size = decision.adjusted_size

        # ── Execute ──
        filled_order = self.broker.submit_order(order)

        if filled_order.filled:
            position = Position(
                symbol=filled_order.symbol,
                direction=filled_order.direction,
                entry_price=filled_order.fill_price,
                quantity=filled_order.quantity,
                stop_loss=envelope.stop_loss,
                tp_levels=envelope.tp_levels,
                entry_time=bar_time,
            )
            self.state.open_position(position)

            log_event(
                self.logger, "info", LogTag.STATE_CHANGE,
                f"Position opened: {position.direction.value} "
                f"{position.quantity}x {position.symbol} @ {position.entry_price:.2f} "
                f"SL={position.stop_loss:.2f}",
            )

        self._set_status("MONITORING")

    def check_exits(self, symbol: str, current_price: float, bar_time: Optional[datetime] = None) -> Optional[float]:
        """
        Check if any open position should be closed (SL hit or TP hit).
        Returns PnL if a position was closed, None otherwise.
        """
        if symbol not in self.state.positions:
            return None

        pos = self.state.positions[symbol]

        # Check stop-loss
        if pos.is_stopped_out(current_price):
            pnl = self.state.close_position(symbol, pos.stop_loss, bar_time)
            log_event(
                self.logger, "info", LogTag.FILL,
                f"STOP-LOSS HIT: {symbol} closed @ {pos.stop_loss:.2f} | PnL: ${pnl:.2f}",
            )
            return pnl

        # Check take-profit levels (use highest TP hit)
        tp_idx = pos.check_tp_hit(current_price)
        if tp_idx is not None:
            tp_price = pos.tp_levels[tp_idx]
            pnl = self.state.close_position(symbol, tp_price, bar_time)
            log_event(
                self.logger, "info", LogTag.FILL,
                f"TP{tp_idx + 1} HIT: {symbol} closed @ {tp_price:.2f} | PnL: ${pnl:.2f}",
            )
            return pnl

        return None

    def _set_status(self, status: str) -> None:
        prev = self.state.status
        self.state.status = status
        if prev != status:
            log_event(
                self.logger, "debug", LogTag.STATE_CHANGE,
                f"State: {prev} → {status}",
            )

    def _handle_shutdown(self) -> None:
        log_event(self.logger, "info", LogTag.SYSTEM, "Shutdown signal received.")
        self._shutdown = True

    async def _cleanup(self) -> None:
        """Graceful shutdown: close positions, disconnect broker."""
        log_event(self.logger, "info", LogTag.SYSTEM, "Cleaning up...")
        self.broker.disconnect()
        self._set_status("SHUTDOWN")
        log_event(
            self.logger, "info", LogTag.SYSTEM,
            f"Agent stopped. Final equity: ${self.state.account.current_equity:.2f} | "
            f"Trades: {self.state.account.total_trades} | "
            f"Win rate: {self.state.account.win_rate:.1f}%",
        )


async def main():
    """Entry point for live agent mode."""
    config = load_config()
    agent = TradingAgent(config=config)
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
