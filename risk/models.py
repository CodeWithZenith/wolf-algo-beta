"""
Wolf Algo — Risk Data Models
==============================
Dataclasses representing trade risk envelopes, risk decisions,
and account-level risk state tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class RiskRejectionReason(str, Enum):
    MISSING_STOP_LOSS = "MISSING_STOP_LOSS"
    MAX_DRAWDOWN_BREACHED = "MAX_DRAWDOWN_BREACHED"
    DAILY_LOSS_LIMIT_HIT = "DAILY_LOSS_LIMIT_HIT"
    MAX_POSITIONS_REACHED = "MAX_POSITIONS_REACHED"
    POSITION_SIZE_TOO_LARGE = "POSITION_SIZE_TOO_LARGE"
    STOP_LOSS_NOT_STRUCTURAL = "STOP_LOSS_NOT_STRUCTURAL"
    INSUFFICIENT_EQUITY = "INSUFFICIENT_EQUITY"


@dataclass
class TradeRiskEnvelope:
    """
    Complete risk parameters for a single trade.
    Every order MUST carry a populated envelope.
    """
    direction: Direction
    entry_price: float
    stop_loss: float
    tp_levels: List[float] = field(default_factory=list)
    position_size: int = 1
    risk_ticks: float = 0.0
    risk_dollars: float = 0.0
    symbol: str = ""
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.entry_price > 0 and self.stop_loss > 0:
            self.risk_ticks = abs(self.entry_price - self.stop_loss)
            self.risk_dollars = self.risk_ticks * self.position_size


@dataclass
class RiskDecision:
    """Result of the risk gatekeeper evaluation."""
    approved: bool
    reason: Optional[RiskRejectionReason] = None
    message: str = ""
    adjusted_size: Optional[int] = None  # If risk manager reduces position size

    @staticmethod
    def approve(message: str = "Order approved") -> "RiskDecision":
        return RiskDecision(approved=True, message=message)

    @staticmethod
    def reject(reason: RiskRejectionReason, message: str = "") -> "RiskDecision":
        return RiskDecision(approved=False, reason=reason, message=message)


@dataclass
class AccountRiskState:
    """
    Real-time account risk tracking.
    Updated on every fill, partial fill, and mark-to-market tick.
    """
    starting_equity: float = 25000.0
    current_equity: float = 25000.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    daily_pnl: float = 0.0
    peak_equity: float = 25000.0
    current_drawdown_pct: float = 0.0
    open_position_count: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    def update_equity(self, pnl_change: float) -> None:
        """Update equity after a trade close or partial fill."""
        self.realized_pnl += pnl_change
        self.daily_pnl += pnl_change
        self.current_equity += pnl_change
        self.peak_equity = max(self.peak_equity, self.current_equity)
        if self.peak_equity > 0:
            self.current_drawdown_pct = (
                (self.peak_equity - self.current_equity) / self.peak_equity * 100
            )
        self.total_trades += 1
        if pnl_change >= 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

    def reset_daily(self) -> None:
        """Reset daily PnL counter (call at session open)."""
        self.daily_pnl = 0.0

    @property
    def win_rate(self) -> float:
        return (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0.0


@dataclass
class Order:
    """Internal order representation."""
    symbol: str
    direction: Direction
    order_type: OrderType
    quantity: int
    price: float  # Limit/stop price, or 0 for market
    risk_envelope: Optional[TradeRiskEnvelope] = None
    order_id: str = ""
    timestamp: Optional[datetime] = None
    filled: bool = False
    fill_price: float = 0.0
    rejected: bool = False
    rejection_reason: str = ""


@dataclass
class Position:
    """Active position tracker."""
    symbol: str
    direction: Direction
    entry_price: float
    quantity: int
    stop_loss: float
    tp_levels: List[float] = field(default_factory=list)
    unrealized_pnl: float = 0.0
    entry_time: Optional[datetime] = None

    def mark_to_market(self, current_price: float) -> float:
        """Calculate unrealized PnL at current price."""
        if self.direction == Direction.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity
        return self.unrealized_pnl

    def is_stopped_out(self, current_price: float) -> bool:
        """Check if current price has hit stop-loss."""
        if self.direction == Direction.LONG:
            return current_price <= self.stop_loss
        return current_price >= self.stop_loss

    def check_tp_hit(self, current_price: float) -> Optional[int]:
        """Check if any TP level is hit, return index or None."""
        for i, tp in enumerate(self.tp_levels):
            if self.direction == Direction.LONG and current_price >= tp:
                return i
            elif self.direction == Direction.SHORT and current_price <= tp:
                return i
        return None
