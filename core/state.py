"""
Wolf Algo — Agent State Management
====================================
Tracks open positions, pending orders, realized PnL, and equity curve.
Serializable to JSON for crash recovery.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional
from risk.models import Position, Order, Direction, AccountRiskState


@dataclass
class AgentState:
    """
    Central state container for the trading agent.
    All mutations flow through this class for auditability.
    """
    # Account state
    account: AccountRiskState = field(default_factory=AccountRiskState)

    # Active positions (keyed by symbol)
    positions: Dict[str, Position] = field(default_factory=dict)

    # Pending orders (keyed by order_id)
    pending_orders: Dict[str, Order] = field(default_factory=dict)

    # Trade history for reporting
    trade_log: List[Dict] = field(default_factory=list)

    # Equity curve (timestamp → equity)
    equity_curve: List[Dict] = field(default_factory=list)

    # Agent lifecycle
    status: str = "IDLE"  # IDLE | LISTENING | EVALUATING | ORDERING | MONITORING | SHUTDOWN

    def open_position(self, position: Position) -> None:
        """Register a new open position."""
        self.positions[position.symbol] = position
        self.account.open_position_count = len(self.positions)

    def close_position(self, symbol: str, exit_price: float, exit_time: Optional[datetime] = None) -> float:
        """
        Close a position and record the trade.
        Returns realized PnL.
        """
        if symbol not in self.positions:
            return 0.0

        pos = self.positions.pop(symbol)

        # Calculate PnL
        if pos.direction == Direction.LONG:
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        self.account.update_equity(pnl)
        self.account.open_position_count = len(self.positions)

        # Log trade
        self.trade_log.append({
            "symbol": symbol,
            "direction": pos.direction.value,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "quantity": pos.quantity,
            "pnl": round(pnl, 2),
            "stop_loss": pos.stop_loss,
            "entry_time": str(pos.entry_time) if pos.entry_time else None,
            "exit_time": str(exit_time) if exit_time else None,
        })

        return pnl

    def record_equity(self, timestamp: datetime) -> None:
        """Snapshot current equity for the equity curve."""
        self.equity_curve.append({
            "timestamp": str(timestamp),
            "equity": round(self.account.current_equity, 2),
            "drawdown_pct": round(self.account.current_drawdown_pct, 2),
        })

    def mark_all_positions(self, prices: Dict[str, float]) -> None:
        """Mark all positions to market."""
        total_unrealized = 0.0
        for symbol, pos in self.positions.items():
            if symbol in prices:
                pos.mark_to_market(prices[symbol])
                total_unrealized += pos.unrealized_pnl
        self.account.unrealized_pnl = total_unrealized

    def to_json(self) -> str:
        """Serialize state to JSON for crash recovery."""
        state = {
            "status": self.status,
            "account": {
                "current_equity": self.account.current_equity,
                "realized_pnl": self.account.realized_pnl,
                "daily_pnl": self.account.daily_pnl,
                "drawdown_pct": self.account.current_drawdown_pct,
                "open_positions": self.account.open_position_count,
                "total_trades": self.account.total_trades,
                "win_rate": self.account.win_rate,
            },
            "positions": {
                sym: {
                    "direction": pos.direction.value,
                    "entry": pos.entry_price,
                    "stop_loss": pos.stop_loss,
                    "quantity": pos.quantity,
                    "unrealized_pnl": pos.unrealized_pnl,
                }
                for sym, pos in self.positions.items()
            },
            "recent_trades": self.trade_log[-10:],  # Last 10 trades
        }
        return json.dumps(state, indent=2, default=str)
