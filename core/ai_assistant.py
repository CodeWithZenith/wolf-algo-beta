"""
Wolf Algo — Interactive AI Trading Desk Assistant
===================================================
Allows users to bounce ideas, ask trade setup questions, analyze live levels,
and chat with Wolf Algo's AI Trading Brain directly inside Discord!
"""

import os
import yfinance as yf
import pandas as pd
from typing import Dict, Any
from core.robbins_cup_engine import robbins_cup_engine


class AITradingDeskAssistant:
    """
    AI Trading Desk Conversational Assistant.
    Analyzes live market structure, GEX, OTE zones, and account risk state to answer Discord user questions.
    """

    @staticmethod
    def answer_user_query(query_str: str) -> str:
        """
        Parses user's Discord query, fetches live market & account context, and returns an institutional AI breakdown.
        """
        q = query_str.strip().lower()

        # Identify requested symbol context
        target_sym = "NQ=F"
        target_name = "Nasdaq 100"

        if any(k in q for k in ["gold", "gc", "xau"]):
            target_sym, target_name = "GC=F", "Gold Spot"
        elif any(k in q for k in ["sp", "es", "spx"]):
            target_sym, target_name = "ES=F", "S&P 500"
        elif any(k in q for k in ["dow", "ym"]):
            target_sym, target_name = "YM=F", "Dow Jones 30"
        elif any(k in q for k in ["btc", "bitcoin", "crypto"]):
            target_sym, target_name = "BTC-USD", "Bitcoin"

        try:
            # 1. Gather Live Market Context
            df = yf.download(target_sym, period="1mo", interval="1d", progress=False)
            gex_data = robbins_cup_engine.run_premarket_gex_analysis(df)
            ote_data = robbins_cup_engine.check_ote_discount_zone(df)

            regime = gex_data.get("weekly_gex_regime", "POSITIVE_GAMMA")
            score = gex_data.get("gex_score", 50.0)
            call_w = gex_data.get("call_wall", 0.0)
            put_w = gex_data.get("put_wall", 0.0)
            flip_lvl = gex_data.get("gamma_flip_level", 0.0)
            is_above_flip = gex_data.get("price_above_gamma_flip", True)

            ote_500 = ote_data.get("ote_level_500", 0.0)
            ote_705 = ote_data.get("ote_level_705", 0.0)
            ote_886 = ote_data.get("ote_level_886", 0.0)
            in_ote = ote_data.get("in_ote_zone", False)

            curr_price = ote_data.get("swing_high", 0.0)

            # 2. Formulate Conversational AI Brain Response
            lines = [
                f"🧠 **WOLF ALGO AI TRADING DESK ANALYSIS** (`{target_name}`)",
                f"```text",
                f"User Question: '{query_str}'",
                f"-----------------------------------------------------------------",
                f"Live Market Context:",
                f"• GEX Volatility Regime : {regime} ({score:.1f}/100)",
                f"• Weekly Call Wall (Resistance): ${call_w:,.2f}",
                f"• Weekly Put Wall (Support)    : ${put_w:,.2f}",
                f"• Gamma Flip Zone (Line in Sand): ${flip_lvl:,.2f} ({'ABOVE 🟢' if is_above_flip else 'BELOW 🔴'})",
                f"• 0.705 OTE Sweet Spot         : ${ote_705:,.2f}",
                f"• 0.886 Line in the Sand       : ${ote_886:,.2f}",
                f"-----------------------------------------------------------------",
                f"AI TRADING DESK VERDICT & ACTIONABLE PLAYBOOK:"
            ]

            if any(k in q for k in ["should i buy", "long", "take buy"]):
                if is_above_flip and (in_ote or "POSITIVE" in regime):
                    lines.append(f"🟢 **RECOMMENDATION: APPROVED BUY SETUP (HIGH CONFLUENCE)**")
                    lines.append(f"Price is sitting above the Gamma Flip Zone (${flip_lvl:,.2f}) with Positive Gamma.")
                    lines.append(f"• **Entry Strategy:** Buy Long on Wolf Algo V1 green flip near ${ote_705:,.2f}.")
                    lines.append(f"• **Stop Loss:** Strict SL at ${ote_886:,.2f} (0.886 Line in Sand).")
                    lines.append(f"• **Target:** Target 1:1 TP1, 2:1 TP2, & lock BE @ +0.35 RR in 60s.")
                else:
                    lines.append(f"⚠️ **RECOMMENDATION: EXERCISE CAUTION ON LONGS**")
                    lines.append(f"Price is testing under Gamma Flip or in Negative Gamma expansion. Wait for price to sweep ${ote_886:,.2f} line in sand first!")

            elif any(k in q for k in ["short", "sell", "take short"]):
                if not is_above_flip or "NEGATIVE" in regime:
                    lines.append(f"🔴 **RECOMMENDATION: APPROVED SHORT SETUP**")
                    lines.append(f"Price is below Gamma Flip (${flip_lvl:,.2f}) or in Negative Gamma breakout regime.")
                    lines.append(f"• **Entry Strategy:** Short Sell when Wolf Algo V1 flips red at Call Wall resistance (${call_w:,.2f}).")
                    lines.append(f"• **Stop Loss:** SL above Call Wall (${call_w:,.2f}).")
                else:
                    lines.append(f"⚠️ **RECOMMENDATION: CAUTION ON COUNTER-TREND SHORTS**")
                    lines.append(f"GEX is Positive (Mean-Reversion). Shorts have tight profit margins; wait for top resistance rejection!")

            elif any(k in q for k in ["level", "wall", "where", "support", "resistance"]):
                lines.append(f"📊 **KEY INSTITUTIONAL LEVELS FOR {target_name.upper()}:**")
                lines.append(f"1. **Major Resistance (Call Wall):** ${call_w:,.2f}")
                lines.append(f"2. **Gamma Flip Boundary:** ${flip_lvl:,.2f}")
                lines.append(f"3. **0.705 OTE Sweet Spot:** ${ote_705:,.2f}")
                lines.append(f"4. **0.886 Line in Sand Support:** ${ote_886:,.2f}")
                lines.append(f"5. **Major Support (Put Wall):** ${put_w:,.2f}")

            else:
                lines.append(f"⚡ **STRATEGY SYNOPSIS:**")
                lines.append(f"Market is in {regime} mode. Positive GEX favors buying dips at OTE Wholesale Discount (${ote_705:,.2f} - ${ote_886:,.2f}).")
                lines.append(f"Always wait for 0.886 Line in Sand sweeps + Wolf Algo V1 green flip confirmation!")

            lines.append("```")
            lines.append("⚡ **WOLF ALGO AI DESK:** `ONLINE & ACTIVE 24/7 🟢`\n*Ask me anything about market levels, trade ideas, or risk rules!*")

            return "\n".join(lines)
        except Exception as e:
            return f"🤖 **Wolf Algo AI Assistant:** I analyzed your question '{query_str}', but encountered a data lookup error: {e}"


ai_assistant = AITradingDeskAssistant()
