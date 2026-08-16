# 🐺 Wolf Algo V1 — Institutional Quantitative Trading System

An elite, modular, Python-based quantitative trading agent featuring **TradeLocker multi-account auto-execution**, **Kakushadze 151 Formulaic Alphas**, **Corporate Finance Institute (CFI) technical models**, **Immutable Risk Guardrails**, and a **24/7 Interactive Discord & Telegram Control Center**.

---

## 🌟 Key Features & Institutional Enhancements

- 🏦 **TradeLocker Direct Execution Engine:**
  - Full multi-account support ($1,000 to $100,000+ accounts).
  - Dynamic Equity-Scaled Lot Sizing (0.10 lots / $50 max risk for $100k; 0.05 lots / $5 max risk for $1k).
  - Microsecond order placement with structural stop loss and take profit attached.
- 🧠 **Quant Supercharger Engine (`core/quant_strategies.py`):**
  - **Kakushadze Strategy 10.4:** Tanh Hyperbolic Momentum Signal Smoothing ($\eta = \tanh(R / \kappa)$) to eliminate noise flipping.
  - **Kakushadze Strategy 6.5 & 7.4:** Volatility Targeting Position Sizing ($w = \sigma_{\text{target}} / \sigma$).
  - **Kakushadze Strategy 8.1:** Hodrick-Prescott (HP) Time-Series Noise Filter.
  - **CFI Pin Bar Scalping Engine:** Rejection candle detection on 5m/15m charts.
  - **CFI TRIN / Arms Index:** Real-time advance/decline breadth market volume ratio.
- 🛡️ **Immutable Constitutional Guardrails (`risk/manager.py`):**
  - Mandatory Structural Stop-Loss (cannot be widened).
  - Hard Daily Loss Circuit Breaker (-$500 on $100k / -$25 on $1k).
  - Adaptive Real-Time Spread Spike Protection (blocks trades if spread expands >2.5x median).
  - Ross Cameron Equities Guardrail ($2–$25 price, RVOL $\ge 2.0$x, float $\le 50$M, $>10\%$ gain).
- 🕒 **Automated Daily Structure & Execution Schedule:**
  - **5:00 PM – 7:00 PM EST (4:00 PM – 6:00 PM CT):** Pre-Market Structure Analysis (PWH, PWL, PDH, PDL & Weekly OBs mapped).
  - **7:00 PM – 12:00 PM EST (6:00 PM – 11:00 AM CT):** Main Execution Window 1 (Asian, London & NY Morning).
  - **12:00 PM – 2:30 PM EST (11:00 AM – 1:30 PM CT):** Mid-Day Consolidation Structure Analysis (0 trades placed, active data mapping).
  - **2:30 PM – 4:00 PM EST (1:30 PM – 3:00 PM CT):** Power Hour Execution Window 2 (Pre-close afternoon breakouts).
- 📲 **Multi-Platform Control Center (Discord & Telegram):**
  - **Discord:** Direct Gateway Listener for typed commands (`!status`, `!report`, `!smc`, `!breadth`, `!news`, `!prop`, `!chart`, `!quant`, `!buy`, `!sell`).
  - **Telegram:** Webhook alert notifications with custom Bot Token & Chat ID support.

---

## 🤖 AI Assistant Onboarding & Configuration Prompts

When an AI assistant (or human user) is setting up **Wolf Algo**, ask the user the following setup questions:

### 📋 Onboarding Questionnaire:
1. **Which Broker / Brand are you using?** (e.g. `GATESFX`, `Tradr`, `KOT4X`, `Coinexx`)
2. **What is your TradeLocker Account ID & Environment URL?** (e.g. `2408565`, `https://demo.tradelocker.com`)
3. **What is your preferred notification platform?**
   - **Option A (Discord):** Requires `DISCORD_BOT_TOKEN` & `DISCORD_WEBHOOK_URL`
   - **Option B (Telegram):** Requires `TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID`
4. **What is your starting account equity?** ($1,000 or $100,000)

---

## 📌 Discord & Telegram Command Cheat Sheet

| Command | Action / Output |
| :--- | :--- |
| `!status` or `pnl` | Live Multi-Account Balance, Equity & Open Positions |
| `!report` or `stats` | Live TradeLocker Real-Time AI Performance Report (Win Rate %, Sharpe, Sortino) |
| `!quant` or `!quant us30` | Quant Supercharger Assessment (Kakushadze Tanh Momentum & CFI Alphas) |
| `!chart` or `!chart nas100` | High-Resolution Dark Mode Technical PNG Chart Image |
| `!prop` or `challenge` | Prop Firm Challenge Evaluation Card (FTMO / FundedNext Safety Caps) |
| `!breadth` or `nas100` | Major Index Breadth Report (NAS100, S&P 500, Dow 30) |
| `!smc` or `sweeps` | Multi-Timeframe (5m, 15m, 1h, 4h) SMC Order Block & Sweep Scanner |
| `!news` or `calendar` | High-Impact Economic News Calendar & Blackout Status |
| `!buy` or `buy` | Instant Market BUY Long ($100k: 0.10 lots / $5 SL) |
| `!sell` or `sell` | Instant Market SELL Short ($100k: 0.10 lots / $5 SL) |
| `!closeall` or `exit` | Close ALL active open positions instantly |

---

## 🐳 Docker Quick Start (Running 24/7)

```bash
# Clone repository
git clone https://github.com/CodeWithZenith/wolf-algo.git
cd wolf-algo

# Create and configure .env file
cp .env.example .env
# Fill in TL_USERNAME, TL_PASSWORD, TL_ACCOUNT_ID, DISCORD_BOT_TOKEN, TELEGRAM_BOT_TOKEN

# Start 24/7 Docker cluster
docker compose up -d --build

# View container status
docker compose ps

# View live container logs
docker compose logs -f wolf-algo-discord
```

---

## 📂 Codebase Architecture

```text
wolf-algo/
├── config/                 # Settings & env variable loaders
│   ├── settings.py         # Config dataclasses & risk parameters
│   └── default_config.yaml # Base configuration parameters
├── core/                   # Core Quantitative Trading Engines
│   ├── agent.py            # Async main execution loop
│   ├── ai_scorer.py        # HMM Latent Regime Classifier & AI Scorer
│   ├── analytics.py        # Live TradeLocker Performance Analytics
│   ├── chart_generator.py  # Matplotlib PNG Chart Image Generator
│   ├── discord_bot.py      # Interactive Discord Gateway Listener
│   ├── equity_scanner.py   # Ross Cameron Equities & Barra Residual Alpha
│   ├── execution.py        # TradeLocker API Direct Execution Engine
│   ├── index_scanner.py    # Major Index Breadth Scanner (NAS100, SP500, Dow30)
│   ├── multi_asset.py      # Multi-Symbol Resolution (Gold, US30, NAS100, EURUSD, BTC)
│   ├── news_calendar.py    # Economic News Calendar & Blackout Engine
│   ├── orderflow.py        # Hawkes Point Process Order Flow Cascade Detector
│   ├── prop_evaluator.py   # Prop Firm Challenge Safety Evaluator
│   ├── quant_strategies.py # Kakushadze 151 Alphas & CFI Quant Engine
│   ├── smc_scanner.py      # Multi-Timeframe SMC Order Block Scanner
│   ├── state.py            # Agent state representation
│   └── webhook.py          # TradingView Webhook Server (Port 5050)
├── data/                   # Data feeds & persistent storage
│   ├── feed.py             # YFinance & CSV data feeds
│   ├── trade_db.py         # Persistent SQLite Database Manager
│   └── trade_history.sqlite# SQLite Trade History Database
├── risk/                   # Risk Management Gatekeeper
│   ├── manager.py          # Constitutional Guardrails & Risk Gatekeeper
│   └── models.py           # Order, Position & Risk Envelope Dataclasses
├── backtest/               # Backtesting & Optimization
│   ├── engine.py           # Replay backtest engine
│   ├── run_backtest.py     # Backtest CLI runner
│   └── sweep.py            # Parameter optimization sweep
├── Dockerfile              # Docker container definition
├── docker-compose.yml      # Multi-service Docker orchestrator
└── README.md               # Documentation & Setup Guide
```

---

## 🌐 Repositories

- **Main Repo:** [CodeWithZenith/wolf-algo](https://github.com/CodeWithZenith/wolf-algo)
- **Beta Repo:** [CodeWithZenith/wolf-algo-beta](https://github.com/CodeWithZenith/wolf-algo-beta)
