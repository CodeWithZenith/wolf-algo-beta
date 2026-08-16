"""
Wolf Algo — 2-Way Interactive Discord Bot Control Center
=========================================================
Listens for 2-way interactive commands directly from your Discord channel!

Supported Commands in Discord:
  • !status / pnl         -> Replies with live account balance, equity, and open positions.
  • !buy / !long          -> Instantly places a 0.05 lot BUY order with $5.00 trailing SL.
  • !sell / !short        -> Instantly places a 0.05 lot SELL SHORT order with $5.00 trailing SL.
  • !closeall / !exit     -> Instantly closes all active open positions on TradeLocker.
  • !stop / !pause        -> Pauses automatic strategy execution.
  • !start / !resume      -> Resumes automatic strategy execution.
  • !hold                 -> Enforces hold mode on current open position.
"""

import os
import sys
import time
import logging
import asyncio
from typing import Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_USER = os.getenv("DISCORD_USER", "Trapquincyjones")

# Control State Flags
BOT_PAUSED = False
HOLD_POSITION_MODE = False


def send_discord_reply(content: str, embed: Optional[dict] = None):
    """Sends reply message to Discord webhook or channel."""
    if not DISCORD_WEBHOOK_URL:
        print(f"💬 DISCORD BOT REPLY: {content}")
        return
    try:
        import requests
        payload = {}
        if content:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"Discord reply error: {e}")


def handle_discord_command(command_str: str) -> str:
    """
    Parses and executes 2-way interactive Discord commands:
      !status, !buy, !sell, !closeall, !stop, !start, !hold
    """
    global BOT_PAUSED, HOLD_POSITION_MODE
    cmd = command_str.strip().lower()

    from core.execution import initialize_client, SYMBOL

    # 1. STATUS / PNL COMMAND
    if cmd in ["!status", "status", "!pnl", "pnl", "!balance", "accounts"]:
        try:
            tl = initialize_client()
            acc_df = tl.get_all_accounts()
            lines = [f"📊 **Wolf Algo Live Profile Status** (`{DISCORD_USER}`)"]
            lines.append(f"• **Bot Auto-Trader Status:** `{'PAUSED ⏸️' if BOT_PAUSED else 'RUNNING 24/7 🚀'}`\n")

            if hasattr(acc_df, "iterrows"):
                for idx, row in acc_df.iterrows():
                    acc_id = row.get("id")
                    acc_name = row.get("name", f"Account #{acc_id}")
                    acc_bal = row.get("accountBalance", 0.0)
                    acc_curr = row.get("currency", "USD")
                    acc_status = row.get("status", "ACTIVE")
                    lines.append(f"🔹 **Account ID `{acc_id}`** ({acc_name}):")
                    lines.append(f"   • Balance: `${acc_bal:,.2f} {acc_curr}` | Status: `{acc_status}`")
            else:
                acc = tl.get_account_state()
                bal = acc.get("balance", 0.0) if isinstance(acc, dict) else 0.0
                pnl = acc.get("todayNet", 0.0) if isinstance(acc, dict) else 0.0
                lines.append(f"• **Balance:** `${bal:,.2f}` | **Today PnL:** `${pnl:,.2f}`")

            pos = tl.get_all_positions()
            pos_count = len(pos) if hasattr(pos, "__len__") else 0
            lines.append(f"\n• **Active Open Positions:** `{pos_count}`")

            return "\n".join(lines)
        except Exception as e:
            return f"❌ Error fetching status: {e}"

    # 2. INSTANT BUY / LONG COMMAND
    elif cmd in ["!buy", "buy", "!long", "long"]:
        try:
            tl = initialize_client()
            acc = tl.get_account_state()
            bal = float(acc.get("balance", 1000.0)) if isinstance(acc, dict) else 1000.0

            if bal >= 50000.0:
                qty = 0.10
                sl_dist = 5.00
                max_risk = 50.00
            else:
                qty = 0.05
                sl_dist = 1.00
                max_risk = 5.00

            from core.execution import resolve_instrument_id
            inst_id = resolve_instrument_id(tl, SYMBOL)
            history = tl.get_price_history(inst_id, resolution="5m", lookback_period="1D")
            if hasattr(history, "iloc") and len(history) > 0:
                curr_price = float(history['c'].iloc[-1])
            elif isinstance(history, list) and len(history) > 0:
                curr_price = float(history[-1]['c'])
            else:
                curr_price = 4350.0

            sl_price = round(curr_price - sl_dist, 2)
            tp_price = round(curr_price + 30.00, 2)

            order_id = tl.create_order(
                instrument_id=inst_id,
                quantity=qty,
                side="buy",
                type_="market",
                stop_loss=sl_price,
                stop_loss_type="absolute",
                take_profit=tp_price,
                take_profit_type="absolute"
            )
            return f"🚀 **DISCORD COMMAND EXECUTED: PLACED BUY LONG ORDER ({qty} Lots)**\n• Entry Price: `${curr_price:.2f}`\n• Instant Stop Loss: `${sl_price:.2f}` (+${sl_dist:.2f} Gold distance | Max Risk: `-${max_risk:.2f}`)\n• Order ID: `{order_id}`"
        except Exception as e:
            return f"❌ Failed to execute BUY command: {e}"

    # 3. INSTANT SELL / SHORT COMMAND
    elif cmd in ["!sell", "sell", "!short", "short"]:
        try:
            tl = initialize_client()
            acc = tl.get_account_state()
            bal = float(acc.get("balance", 1000.0)) if isinstance(acc, dict) else 1000.0

            if bal >= 50000.0:
                qty = 0.10
                sl_dist = 5.00
                max_risk = 50.00
            else:
                qty = 0.05
                sl_dist = 1.00
                max_risk = 5.00

            from core.execution import resolve_instrument_id
            inst_id = resolve_instrument_id(tl, SYMBOL)
            history = tl.get_price_history(inst_id, resolution="5m", lookback_period="1D")
            if hasattr(history, "iloc") and len(history) > 0:
                curr_price = float(history['c'].iloc[-1])
            elif isinstance(history, list) and len(history) > 0:
                curr_price = float(history[-1]['c'])
            else:
                curr_price = 4350.0

            sl_price = round(curr_price + sl_dist, 2)
            tp_price = round(curr_price - 30.00, 2)

            order_id = tl.create_order(
                instrument_id=inst_id,
                quantity=qty,
                side="sell",
                type_="market",
                stop_loss=sl_price,
                stop_loss_type="absolute",
                take_profit=tp_price,
                take_profit_type="absolute"
            )
            return f"📉 **DISCORD COMMAND EXECUTED: PLACED SELL SHORT ORDER ({qty} Lots)**\n• Entry Price: `${curr_price:.2f}`\n• Instant Stop Loss: `${sl_price:.2f}` (+${sl_dist:.2f} Gold distance | Max Risk: `-${max_risk:.2f}`)\n• Order ID: `{order_id}`"
        except Exception as e:
            return f"❌ Failed to execute SELL command: {e}"

    # 4. CLOSE ALL / EXIT COMMAND
    elif cmd in ["!closeall", "closeall", "!exit", "exit", "!close"]:
        try:
            tl = initialize_client()
            pos = tl.get_all_positions()
            closed_count = 0
            if hasattr(pos, "iterrows"):
                for _, p in pos.iterrows():
                    pid = p.get("id") or p.get("positionId")
                    if pid:
                        tl.close_position(position_id=pid)
                        closed_count += 1
            return f"🚨 **DISCORD COMMAND EXECUTED: CLOSED ALL OPEN POSITIONS**\n• Positions Closed: `{closed_count}`"
        except Exception as e:
            return f"❌ Failed to close positions: {e}"

    # 5. STOP / PAUSE COMMAND
    elif cmd in ["!stop", "stop", "!pause", "pause"]:
        BOT_PAUSED = True
        return "⏸️ **DISCORD COMMAND EXECUTED: AUTOMATIC BOT TRADING PAUSED.**\nType `!start` or `resume` to resume 24/7 trading."

    # 6. START / RESUME COMMAND
    elif cmd in ["!start", "start", "!resume", "resume"]:
        BOT_PAUSED = False
        return "🚀 **DISCORD COMMAND EXECUTED: AUTOMATIC BOT TRADING RESUMED 24/7!**"

    # 7. HOLD POSITION COMMAND
    elif cmd in ["!hold", "hold"]:
        HOLD_POSITION_MODE = True
        return "🔒 **DISCORD COMMAND EXECUTED: HOLD POSITION MODE ENABLED.** Holding active trade."

    # 8. EQUITY MOMENTUM SCANNER COMMAND
    elif any(k in cmd for k in ["scan", "equity", "gappers", "top"]):
        try:
            import re
            num_match = re.search(r'\b(100|[1-9]\d?)\b', command_str)
            target_n = int(num_match.group(1)) if num_match else 20

            from core.equity_scanner import fetch_top_equity_gappers, format_gappers_as_table_chunks
            gappers = fetch_top_equity_gappers(top_n=target_n)
            if not gappers:
                return "📊 **Equity Scanner Result:** No stocks currently meet criteria."

            table_chunks = format_gappers_as_table_chunks(gappers, max_items=target_n)
            return table_chunks[0]
        except Exception as e:
            return f"❌ Failed to run equity scanner: {e}"

    # 9. QUANT SUPERCHARGER ALPHAS COMMAND
    elif any(k in cmd for k in ["quant", "alphas", "kakushadze", "cfi"]):
        try:
            from core.multi_asset import normalize_asset_key, get_asset_parameters
            asset_key = normalize_asset_key(command_str)
            asset_info = get_asset_parameters(asset_key)
            yahoo_sym = asset_info["yahoo_symbol"]
            display_name = asset_info["name"]

            import yfinance as yf
            from core.quant_strategies import quant_engine
            df = yf.download(yahoo_sym, period="5d", interval="15m", progress=False)
            res = quant_engine.evaluate_quant_alpha_signal(df)
            return (
                f"🧠 **WOLF ALGO QUANT SUPERCHARGER REPORT** (`{display_name}`)\n"
                f"```text\n"
                f"Target Instrument           | {asset_key} ({display_name})\n"
                f"Quant Score (0-100)         | {res['quant_score']:>3d}/100\n"
                f"Tanh Smoothed Momentum (Eq.477)| {res['tanh_signal']:>+7.3f}\n"
                f"Pin Bar Reversal Pattern    | {res['pin_bar']}\n"
                f"-----------------------------------------------------------------\n"
                f"QUANT CONFLUENCE VERDICT    | {res['verdict']}\n"
                f"```\n"
                f"⚡ **INSTITUTIONAL QUANT STATUS:** `ACTIVE (SUPERCHARGED 🟢)`"
            )
        except Exception as e:
            return f"❌ Failed to run Quant Assessment: {e}"

    # 10. MAJOR INDEX BREADTH & MACRO REGIME SCANNER COMMAND
    elif any(k in cmd for k in ["breadth", "index", "indices"]):
        try:
            from core.index_scanner import format_macro_regime_for_discord
            return format_macro_regime_for_discord()
        except Exception as e:
            return f"❌ Failed to run index breadth scanner: {e}"

    # 11. ECONOMIC NEWS & CALENDAR COMMAND
    elif any(k in cmd for k in ["news", "calendar", "events", "nfp", "cpi", "fomc"]):
        try:
            from core.news_calendar import news_calendar
            return news_calendar.format_news_report_for_discord()
        except Exception as e:
            return f"❌ Failed to run economic news scanner: {e}"

    # 12. SMC INSTITUTIONAL STRUCTURE SCANNER COMMAND
    elif any(k in cmd for k in ["smc", "orderblock", "sweeps", "liquidity", "fvg", "ifvg"]):
        try:
            from core.smc_scanner import smc_scanner
            return smc_scanner.format_smc_report_for_discord()
        except Exception as e:
            return f"❌ Failed to run SMC scanner: {e}"

    # 13. PERFORMANCE ANALYTICS REPORT COMMAND
    elif any(k in cmd for k in ["report", "analytics", "stats", "performance"]):
        try:
            from core.analytics import analytics_engine
            return analytics_engine.format_analytics_report_for_discord()
        except Exception as e:
            return f"❌ Failed to run analytics report: {e}"

    # 14. PROP EVALUATION DASHBOARD COMMAND
    elif any(k in cmd for k in ["prop", "evaluation", "challenge", "ftmo", "funded"]):
        try:
            from core.prop_evaluator import prop_evaluator
            return prop_evaluator.format_prop_report_for_discord()
        except Exception as e:
            return f"❌ Failed to run prop evaluation report: {e}"

    return "Unknown command. Supported: !status, !buy, !sell, !closeall, !stop, !start, !hold, top 10, top 20, !breadth, !report, !smc, !news, !prop, !chart, !quant"


if __name__ == "__main__":
    print("🤖 Starting Wolf Algo Interactive Discord Listener...")
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if token:
        import ssl
        import aiohttp
        import discord

        class WolfDiscordBot(discord.Client):
            async def on_ready(self):
                print(f"🎉 SUCCESS! Logged into Discord Gateway as Bot: {self.user} (ID: {self.user.id})")
                send_discord_reply(f"🟢 **Wolf Algo Discord Gateway Listener Online!** (Bot: `{self.user}`)\nI am now listening to your typed commands in this channel!")

            async def on_message(self, message):
                # Ignore self messages
                if message.author.id == self.user.id:
                    return
                content = message.content.strip()
                if not content:
                    return

                cmd_lower = content.lower()
                keywords = [
                    "pnl", "status", "buy", "sell", "closeall", "exit", "stop", "start", "hold",
                    "pause", "resume", "scan", "equity", "gappers", "top", "breadth", "index",
                    "indices", "nas100", "sp500", "dow30", "report", "analytics", "stats",
                    "performance", "smc", "orderblock", "sweeps", "liquidity", "fvg", "ifvg",
                    "news", "calendar", "events", "nfp", "cpi", "fomc", "prop", "evaluation",
                    "challenge", "ftmo", "funded", "chart", "visual", "candles", "quant",
                    "alphas", "kakushadze", "cfi"
                ]
                if content.startswith("!") or any(k in cmd_lower for k in keywords):
                    print(f"📩 Processing Discord channel command: '{content}' from {message.author}")

                    if any(k in cmd_lower for k in ["chart", "visual", "candles"]):
                        try:
                            from core.multi_asset import normalize_asset_key, get_asset_parameters
                            asset_key = normalize_asset_key(content)
                            asset_info = get_asset_parameters(asset_key)
                            yahoo_sym = asset_info["yahoo_symbol"]
                            display_name = asset_info["name"]

                            from core.chart_generator import generate_chart_image_png
                            png_path = await asyncio.to_thread(generate_chart_image_png, yahoo_sym, display_name)
                            if png_path and os.path.exists(png_path):
                                await message.channel.send(
                                    content=f"📈 **WOLF ALGO REAL-TIME TECHNICAL CHART** (`{display_name}`)",
                                    file=discord.File(png_path)
                                )
                                return
                        except Exception as e:
                            print(f"Chart image upload error: {e}")

                    res = await asyncio.to_thread(handle_discord_command, content)
                    if res and isinstance(res, str):
                        try:
                            await message.channel.send(res)
                        except Exception as e:
                            print(f"Direct channel reply error: {e}")

        intents = discord.Intents.default()
        intents.message_content = True
        client = WolfDiscordBot(intents=intents)
        client.run(token)
    else:
        print("No DISCORD_BOT_TOKEN provided. Webhook dispatch mode active.")
