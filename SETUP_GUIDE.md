# 🛠️ WOLF ALGO BETA — COMPLETE SETUP & ONBOARDING GUIDE

This guide provides step-by-step instructions for deploying **Wolf Algo Beta**, setting up **TradeLocker**, configuring **Discord / Telegram alerts**, and running the agent 24/7.

---

## 🤖 AI ASSISTANT ONBOARDING PROMPT GUIDE

If you are an AI assistant setting up **Wolf Algo** for a user, copy and run the following interactive questionnaire with the user:

```text
Hello! I am ready to set up your Wolf Algo Quantitative Trading Bot.
Please answer the following quick questions so I can configure your system:

1. BROKER / BRAND: Which broker or prop brand are you using? 
   (e.g., GATESFX, Tradr, KOT4X, Coinexx)

2. TRADELOCKER CREDENTIALS:
   - Account ID: (e.g., 2408565 for $100k account)
   - Email / Login:
   - Password:
   - Server Host: (e.g., https://demo.tradelocker.com)

3. NOTIFICATION PLATFORM PREFERENCE:
   - Option A: Discord (Requires DISCORD_BOT_TOKEN & DISCORD_WEBHOOK_URL)
   - Option B: Telegram (Requires TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID)

4. STARTING ACCOUNT CAPITAL:
   - $1,000 Demo Account
   - $100,000 Demo Account
```

---

## 📝 STEP 1: CONFIGURE ENVIRONMENT VARIABLES (`.env`)

Create or edit your `.env` file in the project root directory:

```env
# ---------------------------------------------------------------------------
# TradeLocker Broker API Configuration
# ---------------------------------------------------------------------------
TL_ENVIRONMENT=https://demo.tradelocker.com
TL_USERNAME=focuszenith.info@gmail.com
TL_PASSWORD=YourPasswordHere
TL_SERVER=GATESFX
TL_ACCOUNT_ID=2408565

# ---------------------------------------------------------------------------
# Default Trading Instrument & Lot Sizing
# ---------------------------------------------------------------------------
SYMBOL=XAUUSD
POSITION_QTY=0.10
HARD_DAILY_LOSS_LIMIT=500.0

# ---------------------------------------------------------------------------
# Notification System Setup (Discord vs Telegram)
# ---------------------------------------------------------------------------
# Discord Setup (Option A):
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
DISCORD_USER=Trapquincyjones

# Telegram Setup (Option B - Optional):
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyZ
TELEGRAM_CHAT_ID=987654321

# ---------------------------------------------------------------------------
# Execution Filters & Guardrails
# ---------------------------------------------------------------------------
SESSION_FILTER_ENABLED=true
NEWS_GUARD_ENABLED=true
MAX_ALLOWED_SPREAD=1.50
```

---

## 🐳 STEP 2: LAUNCH DOCKER CLUSTER (24/7 AUTOMATED)

Run the following command to build and launch all 4 background services:

```bash
docker compose up -d --build
```

### Verified Active Services:
- `wolf_algo_execution_bot`: 24/7 TradeLocker execution & indicator engine.
- `wolf_algo_discord_listener`: Interactive Discord channel listener for commands.
- `wolf_algo_equity_scanner`: 24/7 Ross Cameron US Equities momentum scanner.
- `wolf_algo_tradingview_webhook`: TradingView webhook receiver (Port 5050).

---

## 📲 STEP 3: DISCORD CONTROL CENTER COMMANDS

Type any of the following commands in your `#wolf-algo-alerts` Discord channel:

- `!status` $\rightarrow$ Live Multi-Account Balance, Equity & Open Positions
- `!report` $\rightarrow$ Live TradeLocker Real-Time AI Performance Report (Win Rate %, Sharpe, Sortino)
- `!quant` or `!quant us30` $\rightarrow$ Quant Supercharger Assessment (Kakushadze Tanh Momentum & CFI Alphas)
- `!chart` or `!chart nas100` $\rightarrow$ High-Resolution Dark Mode Technical PNG Chart Image
- `!prop` $\rightarrow$ Prop Firm Challenge Evaluation Card (FTMO / FundedNext Safety Caps)
- `!breadth` $\rightarrow$ Major Index Breadth Report (NAS100, S&P 500, Dow 30)
- `!smc` $\rightarrow$ Multi-Timeframe (5m, 15m, 1h, 4h) SMC Order Block & Sweep Scanner
- `!news` $\rightarrow$ High-Impact Economic News Calendar & Blackout Status
- `!buy` $\rightarrow$ Instant Market BUY Long ($100k: 0.10 lots / $5 SL)
- `!sell` $\rightarrow$ Instant Market SELL Short ($100k: 0.10 lots / $5 SL)
- `!closeall` $\rightarrow$ Close ALL active open positions instantly

---

## 🕒 STEP 4: DAILY AUTOMATED TRADING SCHEDULE

Your agent automatically follows this schedule every single day:

- **5:00 PM – 7:00 PM EST (4:00 PM – 6:00 PM CT):** Pre-Market Structure Analysis (PWH, PWL, PDH, PDL & Weekly OBs mapped).
- **7:00 PM – 12:00 PM EST (6:00 PM – 11:00 AM CT):** Main Execution Window 1 (Asian, London & NY Morning).
- **12:00 PM – 2:30 PM EST (11:00 AM – 1:30 PM CT):** Mid-Day Consolidation Structure Analysis (0 trades placed, active data mapping).
- **2:30 PM – 4:00 PM EST (1:30 PM – 3:00 PM CT):** Power Hour Execution Window 2 (Pre-close afternoon breakouts).

---

## 🌐 REPOSITORY LINKS

- **Wolf Algo Main:** [https://github.com/CodeWithZenith/wolf-algo](https://github.com/CodeWithZenith/wolf-algo)
- **Wolf Algo Beta:** [https://github.com/CodeWithZenith/wolf-algo-beta](https://github.com/CodeWithZenith/wolf-algo-beta)
