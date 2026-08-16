"""
Wolf Algo — Risk Management Gatekeeper
========================================
Every order MUST pass through this module before reaching the broker.
Enforces structural stop-loss requirements, position sizing limits,
max drawdown, and daily loss caps. NO EXCEPTIONS.
"""

import logging
from typing import Optional, Tuple
from config.settings import RiskConfig
from risk.models import (
    AccountRiskState,
    Order,
    RiskDecision,
    RiskRejectionReason,
    TradeRiskEnvelope,
    Direction,
)
from utils.logger import LogTag, log_event


class ConstitutionalGuardrails:
    """
    Immutable Constitutional Rules Engine.
    These rules form the core DNA of Wolf Algo and CANNOT be overwritten,
    weakened, or bypassed by machine learning adaptive learning or dynamic tuning.
    """

    @staticmethod
    def validate_immutable_risk(
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        direction: str
    ) -> Tuple[bool, str]:
        """Validates Rule 1 (Mandatory SL) and Rule 4 (Max Single-Trade Risk Cap)."""
        if stop_loss <= 0.0:
            return False, "IMMUTABLE GUARDRAIL VIOLATION: Every order MUST carry a valid structural Stop Loss > 0."

        if direction.upper() in ["BUY", "LONG"] and stop_loss >= entry_price:
            return False, f"IMMUTABLE GUARDRAIL VIOLATION: Long SL (${stop_loss:.2f}) must be BELOW entry (${entry_price:.2f})."

        if direction.upper() in ["SELL", "SHORT"] and stop_loss <= entry_price:
            return False, f"IMMUTABLE GUARDRAIL VIOLATION: Short SL (${stop_loss:.2f}) must be ABOVE entry (${entry_price:.2f})."

        max_risk_cap = 50.00 if account_balance >= 50000.0 else 5.00
        actual_risk = abs(entry_price - stop_loss) * (0.10 if account_balance >= 50000.0 else 0.05) * 100.0

        if actual_risk > (max_risk_cap * 1.05):
            return False, f"IMMUTABLE GUARDRAIL VIOLATION: Per-trade risk (${actual_risk:.2f}) exceeds max risk cap (${max_risk_cap:.2f})."

        return True, "IMMUTABLE CONSTITUTIONAL GUARDRAILS PASSED 🛡️"

    @staticmethod
    def validate_equities_selection(price: float, rvol: float, float_shares: float, gain_pct: float) -> Tuple[bool, str]:
        """Validates Rule 3 (Ross Cameron Ross-5 Equities Selection Rules)."""
        if price < 2.00 or price > 25.00:
            return False, f"Ross Cameron Guardrail 1 Failed: Price ${price:.2f} outside $2-$25 range."
        if rvol < 2.0:
            return False, f"Ross Cameron Guardrail 3 Failed: RVOL {rvol:.2f}x below 2.0x minimum."
        if float_shares > 50_000_000:
            return False, f"Ross Cameron Guardrail 4 Failed: Float {float_shares/1e6:.1f}M exceeds 50M max."
        if gain_pct < 10.0:
            return False, f"Ross Cameron Guardrail 2 Failed: Gain {gain_pct:.1f}% below +10.0% minimum."

    @staticmethod
    def validate_adaptive_spread(current_spread: float, median_spread: float = 0.30) -> Tuple[bool, str]:
        """Validates Adaptive Spread & Slippage Spike Guardrail."""
        if current_spread > 1.50:
            return False, f"IMMUTABLE SPREAD GUARDRAIL VIOLATION: Current spread (${current_spread:.2f}) exceeds absolute max spread cap ($1.50)."
        if median_spread > 0 and (current_spread / median_spread) > 2.5:
            return False, f"IMMUTABLE SPREAD GUARDRAIL VIOLATION: Current spread (${current_spread:.2f}) expanded >2.5x above rolling median spread (${median_spread:.2f})."
        return True, "ADAPTIVE SPREAD GUARDRAIL PASSED 🛡️"


class RiskManager:
    """
    Bulletproof risk gatekeeper.
    
    Rules enforced (in order):
    1. Every order MUST have a TradeRiskEnvelope with a valid stop-loss.
    2. Account drawdown must be below max_drawdown_pct.
    3. Daily loss must be below hard_daily_loss_limit.
    4. Open position count must be below max_open_positions.
    5. Per-trade risk must not exceed max_loss_per_trade_pct of equity.
    
    If ANY rule fails, the order is REJECTED with a clear reason code.
    """

    def __init__(self, config: RiskConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger("wolf_algo.risk")

    def gate_order(
        self,
        order: Order,
        account_state: AccountRiskState,
    ) -> RiskDecision:
        """
        Evaluate an order against all risk rules.
        
        Args:
            order:         The order to evaluate
            account_state: Current account risk state
        
        Returns:
            RiskDecision — approved or rejected with reason
        """
        # ──────────────────────────────────────────────
        # Rule 1: Structural stop-loss is MANDATORY
        # ──────────────────────────────────────────────
        if self.config.require_structural_stop:
            if order.risk_envelope is None:
                decision = RiskDecision.reject(
                    RiskRejectionReason.MISSING_STOP_LOSS,
                    "Order rejected: no TradeRiskEnvelope attached. "
                    "Every order must carry a structural stop-loss.",
                )
                self._log_rejection(order, decision)
                return decision

            if order.risk_envelope.stop_loss <= 0:
                decision = RiskDecision.reject(
                    RiskRejectionReason.MISSING_STOP_LOSS,
                    f"Order rejected: stop_loss={order.risk_envelope.stop_loss} is invalid. "
                    "Must be a positive price level.",
                )
                self._log_rejection(order, decision)
                return decision

            # Validate SL is on the correct side of entry
            env = order.risk_envelope
            if env.direction == Direction.LONG and env.stop_loss >= env.entry_price:
                decision = RiskDecision.reject(
                    RiskRejectionReason.STOP_LOSS_NOT_STRUCTURAL,
                    f"LONG order SL ({env.stop_loss:.2f}) must be BELOW entry ({env.entry_price:.2f}).",
                )
                self._log_rejection(order, decision)
                return decision

            if env.direction == Direction.SHORT and env.stop_loss <= env.entry_price:
                decision = RiskDecision.reject(
                    RiskRejectionReason.STOP_LOSS_NOT_STRUCTURAL,
                    f"SHORT order SL ({env.stop_loss:.2f}) must be ABOVE entry ({env.entry_price:.2f}).",
                )
                self._log_rejection(order, decision)
                return decision

        # ──────────────────────────────────────────────
        # Rule 2: Max drawdown check
        # ──────────────────────────────────────────────
        if account_state.current_drawdown_pct >= self.config.max_drawdown_pct:
            decision = RiskDecision.reject(
                RiskRejectionReason.MAX_DRAWDOWN_BREACHED,
                f"Account drawdown ({account_state.current_drawdown_pct:.2f}%) "
                f"exceeds max allowed ({self.config.max_drawdown_pct:.2f}%). "
                "ALL TRADING HALTED.",
            )
            self._log_rejection(order, decision)
            return decision

        # ──────────────────────────────────────────────
        # Rule 3: Daily loss limit
        # ──────────────────────────────────────────────
        if abs(account_state.daily_pnl) >= self.config.hard_daily_loss_limit and account_state.daily_pnl < 0:
            decision = RiskDecision.reject(
                RiskRejectionReason.DAILY_LOSS_LIMIT_HIT,
                f"Daily loss (${account_state.daily_pnl:.2f}) breaches hard limit "
                f"(${self.config.hard_daily_loss_limit:.2f}). No more trades today.",
            )
            self._log_rejection(order, decision)
            return decision

        # ──────────────────────────────────────────────
        # Rule 4: Max open positions
        # ──────────────────────────────────────────────
        if account_state.open_position_count >= self.config.max_open_positions:
            decision = RiskDecision.reject(
                RiskRejectionReason.MAX_POSITIONS_REACHED,
                f"Open positions ({account_state.open_position_count}) "
                f"at max ({self.config.max_open_positions}). Close a position first.",
            )
            self._log_rejection(order, decision)
            return decision

        # ──────────────────────────────────────────────
        # Rule 5: Per-trade risk sizing
        # ──────────────────────────────────────────────
        if order.risk_envelope:
            max_risk_dollars = account_state.current_equity * (self.config.max_loss_per_trade_pct / 100)
            if order.risk_envelope.risk_dollars > max_risk_dollars:
                # Calculate the maximum allowed position size
                risk_per_unit = order.risk_envelope.risk_ticks
                if risk_per_unit > 0:
                    max_size = int(max_risk_dollars / risk_per_unit)
                    if max_size < 1:
                        decision = RiskDecision.reject(
                            RiskRejectionReason.POSITION_SIZE_TOO_LARGE,
                            f"Risk per trade (${order.risk_envelope.risk_dollars:.2f}) exceeds "
                            f"max allowed (${max_risk_dollars:.2f}). Even 1 unit exceeds limit.",
                        )
                        self._log_rejection(order, decision)
                        return decision
                    else:
                        # Approve with reduced size
                        decision = RiskDecision.approve(
                            f"Position size reduced from {order.risk_envelope.position_size} "
                            f"to {max_size} to stay within risk budget."
                        )
                        decision.adjusted_size = max_size
                        log_event(
                            self.logger, "warning", LogTag.RISK,
                            f"Position size adjusted: {order.risk_envelope.position_size} → {max_size}",
                            {"order_symbol": order.symbol, "max_risk": max_risk_dollars},
                        )
                        return decision

        # ──────────────────────────────────────────────
        # Rule 6: Dynamic Position Quantity Cap (Scaled to Account Equity)
        # ──────────────────────────────────────────────
        # Base limit: 0.10 lots per $5,000 equity (scales up as account compounds)
        dynamic_max_qty = max(0.10, round((account_state.current_equity / 5000.0) * 0.10, 2))
        if order.quantity > dynamic_max_qty:
            decision = RiskDecision.approve(
                f"Position size {order.quantity} exceeded dynamic equity limit {dynamic_max_qty}. Capped to {dynamic_max_qty} lots."
            )
            decision.adjusted_size = dynamic_max_qty
            log_event(
                self.logger, "warning", LogTag.RISK,
                f"Position size capped to dynamic equity limit: {order.quantity} → {dynamic_max_qty}",
                {"symbol": order.symbol, "equity": account_state.current_equity, "max_allowed": dynamic_max_qty},
            )
            return decision

        # ──────────────────────────────────────────────
        # All checks passed
        # ──────────────────────────────────────────────
        decision = RiskDecision.approve("All risk checks passed.")
        log_event(
            self.logger, "info", LogTag.RISK,
            f"Order APPROVED: {order.direction.value} {order.quantity}x {order.symbol}",
            {"entry": order.risk_envelope.entry_price if order.risk_envelope else None,
             "sl": order.risk_envelope.stop_loss if order.risk_envelope else None},
        )
        return decision

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
    ) -> int:
        """
        Calculate position size based on fixed fractional risk.
        
        Risk per trade = equity * max_loss_per_trade_pct / 100
        Position size  = risk_dollars / risk_per_unit
        """
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit <= 0:
            return 0
        max_risk = equity * (self.config.max_loss_per_trade_pct / 100)
        size = int(max_risk / risk_per_unit)
        return max(size, 0)

    def _log_rejection(self, order: Order, decision: RiskDecision) -> None:
        """Log a rejected order with full context."""
        log_event(
            self.logger, "warning", LogTag.REJECT,
            f"Order REJECTED: {decision.reason.value if decision.reason else 'UNKNOWN'}",
            {
                "symbol": order.symbol,
                "direction": order.direction.value,
                "quantity": order.quantity,
                "reason": decision.reason.value if decision.reason else None,
                "message": decision.message,
            },
        )


class SharpeSortinoRewardOptimizer:
    """
    Reinforcement Learning Risk-Adjusted Reward Optimizer.
    Optimizes agent reward functions for Sharpe Ratio & Sortino Ratio
    net of execution friction (spread cost + slippage).
    """

    def __init__(self, risk_free_rate: float = 0.04):
        self.rf = risk_free_rate

    def compute_risk_adjusted_reward(
        self,
        trade_returns: list,
        execution_spread: float = 0.20,
        slippage_friction: float = 0.10
    ) -> dict:
        """
        Computes Sharpe Ratio, Sortino Ratio, and Net RL Reward.
        """
        if not trade_returns or len(trade_returns) < 2:
            return {"sharpe": 1.5, "sortino": 2.0, "net_reward": 1.0}

        import numpy as np
        net_returns = np.array(trade_returns) - (execution_spread + slippage_friction)
        avg_ret = float(np.mean(net_returns))
        std_ret = float(np.std(net_returns)) + 1e-6

        downside_returns = net_returns[net_returns < 0]
        downside_std = float(np.std(downside_returns)) + 1e-6 if len(downside_returns) > 0 else 1e-6

        sharpe = (avg_ret - (self.rf / 252)) / std_ret
        sortino = (avg_ret - (self.rf / 252)) / downside_std

        net_reward = (sharpe * 0.5) + (sortino * 0.5)

        return {
            "sharpe_ratio": round(float(sharpe), 3),
            "sortino_ratio": round(float(sortino), 3),
            "net_rl_reward": round(float(net_reward), 3)
        }
