"""
Wolf Algo — Strategy Base Class
=================================
Abstract interface that all trading strategies must implement.
Ensures consistent signal output for the agent pipeline.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd
from risk.models import Direction


@dataclass
class Signal:
    """
    Strategy output — a single trading signal.
    
    Attributes:
        direction:     LONG, SHORT, or FLAT (no action)
        entry_price:   Suggested entry price
        stop_price:    Structural stop-loss level
        tp_levels:     Take-profit target levels
        strength:      Signal confidence 0.0 → 1.0
        symbol:        Instrument symbol
        position_size: Suggested position size (may be overridden by risk manager)
        metadata:      Extra strategy-specific data (e.g. which TFs confirm)
    """
    direction: Direction = Direction.FLAT
    entry_price: float = 0.0
    stop_price: float = 0.0
    tp_levels: List[float] = field(default_factory=list)
    strength: float = 0.0
    symbol: str = ""
    position_size: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    @property
    def is_entry(self) -> bool:
        return self.direction in (Direction.LONG, Direction.SHORT)

    @property
    def risk_reward_ratio(self) -> float:
        """Best R:R ratio from available TP levels."""
        if not self.tp_levels or self.stop_price == 0 or self.entry_price == 0:
            return 0.0
        risk = abs(self.entry_price - self.stop_price)
        if risk == 0:
            return 0.0
        best_reward = max(abs(tp - self.entry_price) for tp in self.tp_levels)
        return best_reward / risk


class Strategy(ABC):
    """
    Abstract strategy interface.
    
    Subclasses must implement:
      - name:       Human-readable strategy name
      - evaluate:   Process bar data and return a Signal
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging and identification."""
        ...

    @abstractmethod
    def evaluate(self, bars: pd.DataFrame, symbol: str = "") -> Signal:
        """
        Evaluate the strategy on historical/live bar data.
        
        Args:
            bars:   DataFrame with columns: Open, High, Low, Close, Volume
                    Index should be DatetimeIndex.
                    Must contain enough history for indicator warm-up.
            symbol: Instrument symbol
        
        Returns:
            Signal with direction, entry/SL/TP levels, and strength.
            Return Direction.FLAT if no signal on this bar.
        """
        ...

    def warmup_period(self) -> int:
        """Minimum bars needed before strategy can produce valid signals."""
        return 100  # Default — override in subclasses
