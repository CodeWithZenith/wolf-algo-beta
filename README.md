# 🐺 WOLF ALGO BETA — 1-CLICK AUTOMATED SETUP GUIDE

Welcome to **Wolf Algo V6 & Robbins Cup World Champion Trading System**!

This repository is built for **1-click automated setup**. If you drop this zip file or clone this repository into your AI Assistant (Google Antigravity / Cursor / Claude Agent), the assistant can perform the entire setup automatically!

---

## ⚡ AUTOMATED INSTALLATION (FOR AI ASSISTANT)

If you are an AI Assistant reading this codebase, execute the following steps to initialize the environment:

### Step 1: Create Python Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` (or prompt the user for their credentials):
```bash
cp .env.example .env
```
Ensure the following variables are set in `.env`:
- `DISCORD_BOT_TOKEN`: Your Discord bot token for 2-way commands & live alerts.
- `DISCORD_CHANNEL_ID`: Channel ID for alert broadcasts.
- `PAPER_TRADING_MODE`: `true` (default for zero-risk paper trading) or `false` (live execution).

### Step 3: Launch Live Docker Cluster (4 Microservices)
```bash
docker compose up -d --build
```
This launches 4 background microservices:
1. `wolf_algo_execution_bot`: 5-minute execution engine & fast breakeven lock.
2. `wolf_algo_discord_listener`: 25 Discord commands (`!status`, `!news`, `!gex nas`, `!gex btc`).
3. `wolf_algo_equity_scanner`: Market scanner & SMC order block detector.
4. `wolf_algo_tradingview_webhook`: Live TradingView Webhook listener (`port 5050`).

### Step 4: Verify Cluster Health
```bash
docker compose ps
```

---

## 📈 TRADINGVIEW PINE SCRIPT V6 INDICATOR
The TradingView Pine Script v6 indicator code is located in [`scratch/robbins_cup_v6.pine`](scratch/robbins_cup_v6.pine).
1. Copy the contents of `scratch/robbins_cup_v6.pine`.
2. Paste into TradingView Pine Editor (`//@version=6`).
3. Click **Save** and **Add to Chart**.

---

## 🏆 STRATEGY ARCHITECTURE
- **Strategy Engine:** Chris Creamer Robbins Cup Champion (GEX + OTE 0.705-0.886 Fibs + CVD Absorption + 0.886 Line in Sand).
- **Scalper Engine:** 2–3 Minute Lightning Scalper (+0.35 RR Fast Breakeven Lock in 30-120s).
- **Risk Management:** 4-Tier Risk Matrix ($1k, $5k, $25k, $100k account sizing).
