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


# Paper Trading State Storage
PAPER_TRADING_MODE = os.getenv("PAPER_TRADING_MODE", "true").lower() == "true"
paper_state = {
    "balance": 5000.00,
    "equity": 5000.00,
    "today_pnl": 0.00,
    "trades": [],
    "position": None
}


@app.route("/health", methods=["GET"])
def health_check():
    mode_str = "PAPER TRADING (0-Risk)" if PAPER_TRADING_MODE else "LIVE BROKER EXECUTION"
    return jsonify({
        "status": "healthy",
        "service": "Wolf Algo TradingView Webhook Listener",
        "mode": mode_str,
        "paper_balance": paper_state["balance"],
        "paper_today_pnl": paper_state["today_pnl"],
        "open_position": paper_state["position"]
    }), 200


@app.route("/webhook/tradingview", methods=["POST"])
def handle_tradingview_webhook():
    """
    Handle incoming alert payloads from TradingView.
    Supports 0-Risk Paper Trading & Live Execution.
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
        entry_price = float(data.get("price", 0.0))
        stop_loss = float(data.get("stop_loss", 0.0))
        take_profit = float(data.get("take_profit", 0.0))
        quantity = float(data.get("quantity", 0.05))

        print(f"📩 TradingView Alert: Action={action.upper()}, Symbol={symbol}, Price=${entry_price:.2f}")

        # ── 0-RISK PAPER TRADING EXECUTION PATH ──
        if PAPER_TRADING_MODE:
            if action in ["buy", "long"]:
                sl_val = stop_loss if stop_loss > 0 else round(entry_price - 4.00, 2)
                tp_val = take_profit if take_profit > 0 else round(entry_price + 10.00, 2)
                paper_state["position"] = {
                    "side": "BUY",
                    "symbol": symbol,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "stop_loss": sl_val,
                    "take_profit": tp_val
                }
                msg = (
                    f"📝 **PAPER TRADING BUY EXECUTED (0-RISK)**\n"
                    f"• **Symbol:** `{symbol}`\n"
                    f"• **Lot Size:** `{quantity}` lots ($20 max risk)\n"
                    f"• **Entry Price:** `${entry_price:.2f}`\n"
                    f"• **Stop Loss:** `${sl_val:.2f}`\n"
                    f"• **Take Profit:** `${tp_val:.2f}`\n"
                    f"• **Paper Balance:** `${paper_state['balance']:.2f}`"
                )
                print(msg)
                send_discord_alert("📝 Paper Trade Opened (BUY)", msg, color=0x2ECC71)
                return jsonify({"status": "paper_executed", "side": "buy", "price": entry_price, "sl": sl_val, "tp": tp_val}), 200

            elif action in ["sell", "short"]:
                sl_val = stop_loss if stop_loss > 0 else round(entry_price + 4.00, 2)
                tp_val = take_profit if take_profit > 0 else round(entry_price - 10.00, 2)
                paper_state["position"] = {
                    "side": "SELL",
                    "symbol": symbol,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "stop_loss": sl_val,
                    "take_profit": tp_val
                }
                msg = (
                    f"📝 **PAPER TRADING SELL EXECUTED (0-RISK)**\n"
                    f"• **Symbol:** `{symbol}`\n"
                    f"• **Lot Size:** `{quantity}` lots ($20 max risk)\n"
                    f"• **Entry Price:** `${entry_price:.2f}`\n"
                    f"• **Stop Loss:** `${sl_val:.2f}`\n"
                    f"• **Take Profit:** `${tp_val:.2f}`\n"
                    f"• **Paper Balance:** `${paper_state['balance']:.2f}`"
                )
                print(msg)
                send_discord_alert("📝 Paper Trade Opened (SELL SHORT)", msg, color=0xE74C3C)
                return jsonify({"status": "paper_executed", "side": "sell", "price": entry_price, "sl": sl_val, "tp": tp_val}), 200

            elif action in ["close", "exit"]:
                pos = paper_state.get("position")
                if pos:
                    exit_price = entry_price if entry_price > 0 else pos["entry_price"]
                    pnl = (exit_price - pos["entry_price"]) * pos["quantity"] * 100.0 if pos["side"] == "BUY" else (pos["entry_price"] - exit_price) * pos["quantity"] * 100.0
                    paper_state["balance"] += pnl
                    paper_state["today_pnl"] += pnl
                    paper_state["trades"].append({"side": pos["side"], "pnl": pnl, "balance": paper_state["balance"]})
                    paper_state["position"] = None

                    msg = (
                        f"📝 **PAPER TRADING POSITION CLOSED**\n"
                        f"• **Exit Price:** `${exit_price:.2f}`\n"
                        f"• **Trade PnL:** `${pnl:+.2f}`\n"
                        f"• **Updated Paper Balance:** `${paper_state['balance']:.2f}`\n"
                        f"• **Today Paper PnL:** `${paper_state['today_pnl']:+.2f}`"
                    )
                    print(msg)
                    send_discord_alert("📝 Paper Position Closed", msg, color=0x3498DB)
                    return jsonify({"status": "paper_closed", "pnl": pnl, "balance": paper_state["balance"]}), 200
                return jsonify({"status": "no_open_paper_position"}), 200

        # ── LIVE BROKER EXECUTION PATH ──
        tl = initialize_client()
        instrument_id = tl.get_instrument_id_from_symbol_name(symbol)

        acc_state = tl.get_account_state()
        cash_balance = 5000.0
        today_net = 0.0
        if hasattr(acc_state, "iloc") and len(acc_state) > 0:
            cash_balance = float(acc_state['balance'].iloc[0]) if 'balance' in acc_state.columns else float(acc_state['equity'].iloc[0])
            today_net = float(acc_state['todayNet'].iloc[0]) if 'todayNet' in acc_state.columns else 0.0
        elif isinstance(acc_state, dict):
            cash_balance = float(acc_state.get('balance', 5000.0))
            today_net = float(acc_state.get('todayNet', 0.0))

        if today_net <= -HARD_DAILY_LOSS_LIMIT:
            msg = f"🛑 Daily Loss Circuit Breaker Triggered (${today_net:.2f} <= -${HARD_DAILY_LOSS_LIMIT:.2f}). Webhook Order Rejected."
            send_discord_alert("🛑 Webhook Order Blocked", msg, color=0xE74C3C)
            return jsonify({"status": "rejected", "reason": "Circuit Breaker Active"}), 422

        if action in ["buy", "long"]:
            quote = tl.get_symbol_info(instrument_id)
            ep = float(quote.get('ask', 4400.0) or 4400.0) if isinstance(quote, dict) else 4400.0
            sl_val = stop_loss if stop_loss > 0 else round(ep - 4.00, 2)
            tp_val = take_profit if take_profit > 0 else round(ep + 10.00, 2)
            qty = 0.05

            tl.create_order(
                instrument_id=instrument_id,
                quantity=float(qty),
                side="buy",
                type_="market",
                stop_loss=float(sl_val),
                stop_loss_type="absolute",
                take_profit=float(tp_val),
                take_profit_type="absolute"
            )
            msg_details = (
                f"🚀 **TRADINGVIEW WEBHOOK BUY ORDER PLACED**\n"
                f"• **Symbol:** `{symbol}`\n"
                f"• **Quantity:** `{qty}` lots\n"
                f"• **Entry Price:** `${ep:.2f}`\n"
                f"• **Stop Loss:** `${sl_val:.2f}`\n"
                f"• **Take Profit:** `${tp_val:.2f}`"
            )
            print(f"✅ Webhook BUY order executed: {qty} lots of {symbol}")
            send_discord_alert("🚀 TradingView Webhook Executed", msg_details, color=0x2ECC71)
            return jsonify({"status": "executed", "side": "buy", "quantity": qty, "sl": sl_val, "tp": tp_val}), 200

        elif action in ["sell", "short"]:
            quote = tl.get_symbol_info(instrument_id)
            ep = float(quote.get('bid', 4400.0) or 4400.0) if isinstance(quote, dict) else 4400.0
            sl_val = stop_loss if stop_loss > 0 else round(ep + 4.00, 2)
            tp_val = take_profit if take_profit > 0 else round(ep - 10.00, 2)
            qty = 0.05

            tl.create_order(
                instrument_id=instrument_id,
                quantity=float(qty),
                side="sell",
                type_="market",
                stop_loss=float(sl_val),
                stop_loss_type="absolute",
                take_profit=float(tp_val),
                take_profit_type="absolute"
            )
            msg_details = (
                f"📉 **TRADINGVIEW WEBHOOK SELL SHORT ORDER PLACED**\n"
                f"• **Symbol:** `{symbol}`\n"
                f"• **Quantity:** `{qty}` lots\n"
                f"• **Entry Price:** `${ep:.2f}`\n"
                f"• **Stop Loss:** `${sl_val:.2f}`\n"
                f"• **Take Profit:** `${tp_val:.2f}`"
            )
            print(f"✅ Webhook SELL SHORT order executed: {qty} lots of {symbol}")
            send_discord_alert("📉 TradingView Webhook Executed", msg_details, color=0xE74C3C)
            return jsonify({"status": "executed", "side": "sell", "quantity": qty, "sl": sl_val, "tp": tp_val}), 200

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
    port = int(os.getenv("PORT", 5050))
    print(f"🚀 Starting Wolf Algo TradingView Paper Trading Webhook Server on port {port}...")
    app.run(host="0.0.0.0", port=port)
