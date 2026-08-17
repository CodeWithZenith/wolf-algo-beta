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
    Analyzes live market structure, GEX, OTE zones, and account risk state to answer Discord user questions
    in natural, friendly, expert trading dialogue.
    """

    @staticmethod
    def answer_user_query(query_str: str) -> str:
        """
        Parses user's Discord query, fetches live market & account context, and returns a natural conversational AI response.
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

            ote_705 = ote_data.get("ote_level_705", 0.0)
            ote_886 = ote_data.get("ote_level_886", 0.0)
            in_ote = ote_data.get("in_ote_zone", False)

            # 2. Conversational Dialogue Generator (Natural Pair-Trading Persona)
            if any(k in q for k in ["hello", "hi", "hey", "sup", "yo"]):
                return (
                    f"Hey! 🐺 Wolf Algo AI Trading Desk here! I'm actively monitoring live orderflow across Gold, NQ, ES, Dow, and BTC.\n\n"
                    f"Right now on **{target_name}**, we are in `{regime}` mode (Score: {score:.1f}/100) with Gamma Flip at **${flip_lvl:,.2f}**.\n"
                    f"What symbol or setup do you want to bounce ideas on right now?"
                )

            if any(k in q for k in ["should i buy", "long", "take buy", "buy nq", "buy gold"]):
                if is_above_flip and (in_ote or "POSITIVE" in regime):
                    return (
                        f"🟢 **That's an A+ Buy Setup on {target_name}!**\n\n"
                        f"Here is why I like it:\n"
                        f"1. **Market Structure:** Price is sitting ABOVE our Gamma Flip Zone (**${flip_lvl:,.2f}**) in `{regime}` mode.\n"
                        f"2. **Wholesale Pricing:** We are near the 0.705–0.886 OTE Wholesale Discount zone (**${ote_705:,.2f} – ${ote_886:,.2f}**).\n"
                        f"3. **Execution Plan:** Enter when **Wolf Algo V1** flips green. Set SL right below the 0.886 Line in the Sand (**${ote_886:,.2f}**).\n"
                        f"4. **The Law:** Lock Breakeven @ +0.35 RR in 60s, then ratchet SL to TP1, TP2, and trail TP3!"
                    )
                else:
                    return (
                        f"⚠️ **I'd exercise caution on Longs right now for {target_name}.**\n\n"
                        f"Price is currently testing under our Gamma Flip Zone (**${flip_lvl:,.2f}**). "
                        f"I'd wait for price to sweep down near our 0.886 Line in the Sand (**${ote_886:,.2f}**) and print a clean **Wolf Algo V1 Green Flip 🚀** before pulling the trigger!"
                    )

            if any(k in q for k in ["short", "sell", "take short"]):
                if not is_above_flip or "NEGATIVE" in regime:
                    return (
                        f"🔴 **That Short Setup has strong institutional backing on {target_name}!**\n\n"
                        f"Price is below the Gamma Flip Zone (**${flip_lvl:,.2f}**) in Negative Gamma expansion mode. "
                        f"Enter when Wolf Algo V1 flips red at Call Wall resistance (**${call_w:,.2f}**) and target the Put Wall support (**${put_w:,.2f}**)!"
                    )
                else:
                    return (
                        f"⚠️ **Watch out on counter-trend shorts right now.**\n\n"
                        f"GEX is Positive on {target_name} ({score:.1f}/100), meaning dealers are buying dips. "
                        f"Unless price hits top Call Wall resistance (**${call_w:,.2f}**) and rejects, counter-trend shorts have tight profit margins!"
                    )

            if any(k in q for k in ["level", "wall", "where", "support", "resistance"]):
                return (
                    f"📊 **Here are the key institutional levels for {target_name.upper()}:**\n\n"
                    f"• 🏰 **Call Wall (Major Resistance):** `${call_w:,.2f}`\n"
                    f"• ⚖️ **Gamma Flip Zone (Line in Sand):** `${flip_lvl:,.2f}` ({'ABOVE 🟢' if is_above_flip else 'BELOW 🔴'})\n"
                    f"• 🎯 **0.705 OTE Sweet Spot:** `${ote_705:,.2f}`\n"
                    f"• 🛑 **0.886 Line in Sand Support:** `${ote_886:,.2f}`\n"
                    f"• 🛡️ **Put Wall (Major Support):** `${put_w:,.2f}`"
                )

            # Default Conversational Trading Advice
            return (
                f"🧠 **Wolf Algo AI Desk Analysis for {target_name}:**\n\n"
                f"Market is currently in `{regime}` mode ({score:.1f}/100) with Gamma Flip at **${flip_lvl:,.2f}**.\n\n"
                f"**Our Trading Playbook:**\n"
                f"• Wholesale Buy Zone: **${ote_705:,.2f} – ${ote_886:,.2f}**\n"
                f"• 0.886 Invalidation Line: **${ote_886:,.2f}**\n"
                f"• Call Wall Resistance: **${call_w:,.2f}**\n\n"
                f"Whenever price sweeps the 0.886 Line in the Sand and **Wolf Algo V1 flips green**, that is our A+ high-probability entry! What setup are you looking at right now?"
            )

        except Exception as e:
            return f"🤖 **Wolf Algo AI Assistant:** I analyzed your question '{query_str}', but encountered a data lookup error: {e}"


ai_assistant = AITradingDeskAssistant()
