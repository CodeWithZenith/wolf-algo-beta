"""
Wolf Algo — Test Suite: Risk Manager
======================================
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config.settings import RiskConfig
from risk.manager import RiskManager
from risk.models import (
    AccountRiskState,
    Direction,
    Order,
    OrderType,
    RiskRejectionReason,
    TradeRiskEnvelope,
)


@pytest.fixture
def risk_config():
    return RiskConfig(
        max_drawdown_pct=5.0,
        max_loss_per_trade_pct=1.0,
        hard_daily_loss_limit=500.0,
        max_open_positions=3,
        require_structural_stop=True,
    )


@pytest.fixture
def risk_manager(risk_config):
    return RiskManager(risk_config)


@pytest.fixture
def healthy_account():
    return AccountRiskState(
        starting_equity=25000.0,
        current_equity=25000.0,
        peak_equity=25000.0,
        daily_pnl=0.0,
        open_position_count=0,
    )


def _make_order(direction=Direction.LONG, entry=100.0, sl=98.0, qty=1, symbol="SPY"):
    envelope = TradeRiskEnvelope(
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        tp_levels=[102.0, 104.0, 106.0],
        position_size=qty,
        symbol=symbol,
    )
    return Order(
        symbol=symbol,
        direction=direction,
        order_type=OrderType.MARKET,
        quantity=qty,
        price=entry,
        risk_envelope=envelope,
    )


# ── Test: Order with no risk envelope ──
class TestMissingStopLoss:
    def test_reject_no_envelope(self, risk_manager, healthy_account):
        order = Order(
            symbol="SPY",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            quantity=1,
            price=100.0,
            risk_envelope=None,
        )
        decision = risk_manager.gate_order(order, healthy_account)
        assert not decision.approved
        assert decision.reason == RiskRejectionReason.MISSING_STOP_LOSS

    def test_reject_zero_stop_loss(self, risk_manager, healthy_account):
        envelope = TradeRiskEnvelope(
            direction=Direction.LONG,
            entry_price=100.0,
            stop_loss=0.0,
            position_size=1,
        )
        order = Order(
            symbol="SPY",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            quantity=1,
            price=100.0,
            risk_envelope=envelope,
        )
        decision = risk_manager.gate_order(order, healthy_account)
        assert not decision.approved
        assert decision.reason == RiskRejectionReason.MISSING_STOP_LOSS

    def test_reject_sl_wrong_side_long(self, risk_manager, healthy_account):
        """LONG with SL above entry should be rejected."""
        order = _make_order(direction=Direction.LONG, entry=100.0, sl=102.0)
        decision = risk_manager.gate_order(order, healthy_account)
        assert not decision.approved
        assert decision.reason == RiskRejectionReason.STOP_LOSS_NOT_STRUCTURAL

    def test_reject_sl_wrong_side_short(self, risk_manager, healthy_account):
        """SHORT with SL below entry should be rejected."""
        order = _make_order(direction=Direction.SHORT, entry=100.0, sl=98.0)
        decision = risk_manager.gate_order(order, healthy_account)
        assert not decision.approved
        assert decision.reason == RiskRejectionReason.STOP_LOSS_NOT_STRUCTURAL


# ── Test: Drawdown breach ──
class TestDrawdownBreach:
    def test_reject_on_max_drawdown(self, risk_manager):
        account = AccountRiskState(
            starting_equity=25000.0,
            current_equity=23500.0,
            peak_equity=25000.0,
            current_drawdown_pct=6.0,  # Above 5% limit
        )
        order = _make_order()
        decision = risk_manager.gate_order(order, account)
        assert not decision.approved
        assert decision.reason == RiskRejectionReason.MAX_DRAWDOWN_BREACHED


# ── Test: Daily loss limit ──
class TestDailyLossLimit:
    def test_reject_on_daily_loss(self, risk_manager):
        account = AccountRiskState(
            starting_equity=25000.0,
            current_equity=24400.0,
            peak_equity=25000.0,
            daily_pnl=-600.0,  # Above $500 limit
        )
        order = _make_order()
        decision = risk_manager.gate_order(order, account)
        assert not decision.approved
        assert decision.reason == RiskRejectionReason.DAILY_LOSS_LIMIT_HIT


# ── Test: Max positions ──
class TestMaxPositions:
    def test_reject_at_max_positions(self, risk_manager):
        account = AccountRiskState(
            starting_equity=25000.0,
            current_equity=25000.0,
            peak_equity=25000.0,
            open_position_count=3,  # At limit
        )
        order = _make_order()
        decision = risk_manager.gate_order(order, account)
        assert not decision.approved
        assert decision.reason == RiskRejectionReason.MAX_POSITIONS_REACHED


# ── Test: Successful approval ──
class TestApproval:
    def test_valid_order_approved(self, risk_manager, healthy_account):
        order = _make_order(direction=Direction.LONG, entry=100.0, sl=98.0, qty=1)
        decision = risk_manager.gate_order(order, healthy_account)
        assert decision.approved

    def test_valid_short_approved(self, risk_manager, healthy_account):
        order = _make_order(direction=Direction.SHORT, entry=100.0, sl=102.0, qty=1)
        decision = risk_manager.gate_order(order, healthy_account)
        assert decision.approved


# ── Test: Position sizing ──
class TestPositionSizing:
    def test_calculate_position_size(self, risk_manager):
        size = risk_manager.calculate_position_size(
            equity=25000.0,
            entry_price=100.0,
            stop_loss=98.0,
        )
        # Risk per trade: 25000 * 1% = $250
        # Risk per unit: $2
        # Size: 250 / 2 = 125
        assert size == 125

    def test_zero_risk_returns_zero(self, risk_manager):
        size = risk_manager.calculate_position_size(
            equity=25000.0,
            entry_price=100.0,
            stop_loss=100.0,  # No risk distance
        )
        assert size == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
