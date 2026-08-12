"""
Wolf Algo — TradingView Webhook Integration Module
====================================================
Provides an HTTP webhook server to receive automated trade alerts from TradingView
and route them safely through RiskManager to TradeLocker API.
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask, request, jsonify

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.execution import initialize_client, send_discord_alert
from risk.manager import RiskManager
from config.settings import RiskConfig
from risk.models import Order, Direction, OrderType, TradeRiskEnvelope, AccountRiskState

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "wolf_algo_secret_key_2026")
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
MAX_LOSS_DOLLARS = float(os.getenv("MAX_LOSS_DOLLARS", "50.0"))
HARD_DAILY_LOSS_LIMIT = float(os.getenv("HARD_DAILY_LOSS_LIMIT", "125.0"))


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "service": "Wolf Algo TradingView Webhook Listener"}), 200


@app.route("/webhook/tradingview", methods=["POST"])
def handle_tradingview_webhook():
    """
    Handle incoming alert payloads from TradingView.
    
    Expected JSON format from TradingView Alert:
    {
        "passphrase": "wolf_algo_secret_key_2026",
        "action": "buy",
        "symbol": "XAUUSD",
        "quantity": 0.10,
        "stop_loss": 4390.00,
        "take_profit": 4475.00
    }
    """
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON payload provided"}), 400

        # 1. Security Passphrase Check
        passphrase = data.get("passphrase", "")
        if passphrase != WEBHOOK_PASSPHRASE:
            print("🛑 Unauthorized Webhook Attempt: Invalid Passphrase")
            return jsonify({"error": "Unauthorized passphrase"}), 401

        action = str(data.get("action", "")).lower()
        symbol = str(data.get("symbol", SYMBOL)).upper()
        stop_loss = float(data.get("stop_loss", 0.0))
        take_profit = float(data.get("take_profit", 0.0))

        print(f"📩 Webhook Alert Received from TradingView: Action={action.upper()}, Symbol={symbol}")

        tl = initialize_client()
        instrument_id = tl.get_instrument_id_from_symbol_name(symbol)

        # Get Account Balance & Today's PnL
        acc_state = tl.get_account_state()
        cash_balance = 5000.0
        today_net = 0.0
        if hasattr(acc_state, "iloc") and len(acc_state) > 0:
            cash_balance = float(acc_state['balance'].iloc[0]) if 'balance' in acc_state.columns else float(acc_state['equity'].iloc[0])
            today_net = float(acc_state['todayNet'].iloc[0]) if 'todayNet' in acc_state.columns else 0.0
        elif isinstance(acc_state, dict):
            cash_balance = float(acc_state.get('balance', 5000.0))
            today_net = float(acc_state.get('todayNet', 0.0))

        # Check Circuit Breaker
        if today_net <= -HARD_DAILY_LOSS_LIMIT:
            msg = f"🛑 Daily Loss Circuit Breaker Triggered (${today_net:.2f} <= -${HARD_DAILY_LOSS_LIMIT:.2f}). Webhook Order Rejected."
            send_discord_alert("🛑 Webhook Order Blocked", msg, color=0xE74C3C)
            return jsonify({"status": "rejected", "reason": "Circuit Breaker Active"}), 422

        if action in ["buy", "long"]:
            # Calculate Risk & Quantity
            quote = tl.get_symbol_info(instrument_id)
            entry_price = float(quote.get('ask', 4400.0) or 4400.0) if isinstance(quote, dict) else 4400.0
            
            price_stop_dist = abs(entry_price - stop_loss) if stop_loss > 0 else 35.0
            if stop_loss == 0.0:
                stop_loss = round(entry_price - 35.0, 2)
                price_stop_dist = 35.0
            
            if take_profit == 0.0:
                take_profit = round(entry_price + (price_stop_dist * 2.5), 2)

            risk_budget = max(MAX_LOSS_DOLLARS, round(cash_balance * 0.01, 2))
            qty = max(0.01, round(risk_budget / (price_stop_dist * 100.0), 2))

            # Gate order through RiskManager
            rm = RiskManager(RiskConfig())
            trade_envelope = TradeRiskEnvelope(
                max_risk_dollars=MAX_LOSS_DOLLARS,
                position_size=qty,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            order_obj = Order(
                symbol=symbol,
                quantity=qty,
                side=Direction.LONG,
                order_type=OrderType.MARKET,
                risk_envelope=trade_envelope
            )
            risk_acc_state = AccountRiskState(
                account_id="tl_webhook",
                current_equity=cash_balance,
                daily_pnl=today_net,
                peak_equity=cash_balance,
                open_positions=[]
            )
            decision = rm.gate_order(order_obj, risk_acc_state)
            if not decision.approved:
                print(f"🛑 Webhook Order REJECTED by RiskManager: {decision.message}")
                return jsonify({"status": "rejected", "reason": decision.message}), 422

            if decision.adjusted_size and decision.adjusted_size < qty:
                qty = decision.adjusted_size

            # Place Order on TradeLocker
            tl.create_order(
                instrument_id=instrument_id,
                quantity=float(qty),
                side="buy",
                type_="market",
                stop_loss=float(stop_loss),
                stop_loss_type="absolute",
                take_profit=float(take_profit),
                take_profit_type="absolute"
            )

            msg_details = (
                f"🚀 **TRADINGVIEW WEBHOOK BUY ORDER PLACED**\n"
                f"• **Symbol:** `{symbol}`\n"
                f"• **Quantity:** `{qty}` lots\n"
                f"• **Entry Price:** `${entry_price:.2f}`\n"
                f"• **Stop Loss:** `${stop_loss:.2f}`\n"
                f"• **Take Profit:** `${take_profit:.2f}`"
            )
            print(f"✅ Webhook BUY order executed: {qty} lots of {symbol}")
            send_discord_alert("🚀 TradingView Webhook Executed", msg_details, color=0x2ECC71)
            return jsonify({"status": "executed", "side": "buy", "quantity": qty, "sl": stop_loss, "tp": take_profit}), 200

        elif action in ["close", "exit"]:
            positions = tl.get_all_positions()
            closed_count = 0
            if hasattr(positions, "iterrows"):
                for idx, p in positions.iterrows():
                    pos_id = p.get('id') if 'id' in p else p.get('positionId')
                    if pos_id:
                        tl.close_position(position_id=pos_id)
                        closed_count += 1
            msg_exit = f"🔒 **TRADINGVIEW WEBHOOK CLOSE EXECUTED**\n• Closed `{closed_count}` open positions."
            send_discord_alert("🔒 TradingView Webhook Close", msg_exit, color=0x3498DB)
            return jsonify({"status": "executed", "action": "close", "closed_positions": closed_count}), 200

        return jsonify({"error": f"Unknown action '{action}'"}), 400

    except Exception as e:
        print(f"Webhook Execution Error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Starting Wolf Algo TradingView Webhook Server on port {port}...")
    app.run(host="0.0.0.0", port=port)
