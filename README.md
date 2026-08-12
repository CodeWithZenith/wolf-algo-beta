# 🐺 Wolf Algo — Public Beta Release

> **Algorithmic Trading Agent with TradeLocker API Execution & Institutional Risk Management**

Welcome to the **Wolf Algo Beta Testing Program**! This repository contains the full automated execution bot, backtesting suite, and risk engine tuned for **Gold (`XAUUSD`)** and equity index trading.

---

## ⚡ Quick Start Guide (Beta Testers)

### Step 1: Clone the Repository
```bash
git clone https://github.com/CodeWithZenith/wolf-algo-beta.git
cd wolf-algo-beta
```

### Step 2: Configure Your Credentials
Copy `.env.example` to `.env` and enter your TradeLocker account credentials:

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in your details:
```env
TL_ENVIRONMENT=https://demo.tradelocker.com
TL_USERNAME=your_tradelocker_email@example.com
TL_PASSWORD=your_tradelocker_password
TL_SERVER=Demo   # or your broker's server name

SYMBOL=XAUUSD
MAX_LOSS_DOLLARS=50.0            # Strict $50 max loss per trade
POSITION_QTY=0.10                # 0.10 lots (10 oz Gold)
HARD_DAILY_LOSS_LIMIT=125.0      # Hard $125 daily loss circuit breaker
```

---

### Step 3: Run 24/7 in Docker (Recommended)

Start the bot in detached background mode:
```bash
docker compose up -d wolf-algo-bot
```

To view live real-time execution logs:
```bash
docker logs -f wolf_algo_execution_bot
```

To stop the bot at any time:
```bash
docker compose stop wolf-algo-bot
```

---

## 🧪 Alternative: Running Locally with Python

If you prefer running directly with Python:

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the live TradeLocker bot
python core/execution.py

# 4. Run historical backtest
python -m backtest.run_backtest --symbol GC=F --equity 4955.18 --daily-loss 125 --risk-pct 1.0

# 5. Run test suite
python -m pytest tests/ -v
```

---

## 🛡️ Integrated Risk Management Features

- **Automated Trailing Stop (`trailingOffset`):** Calculates exact dollar risk per trade ($50 max loss). As price advances in your favor, the stop loss automatically trails up to lock in profit.
- **3:1 Take Profit Target:** Automatically sets a Take Profit target ($150 gain for 3:1 R:R).
- **Regime Shift Exit:** Continuously evaluates the HMA-250 trend filter. If trend reverses, the bot automatically exits the position to secure accumulated gains.
- **Daily Loss Circuit Breaker ($125):** Halts trade entries for the day if net daily losses reach -$125.00, protecting you from prop-firm hard breaches.

---

## 📬 Feedback & Support

For bug reports or feedback during the beta test, please open an Issue on [GitHub Repository](https://github.com/CodeWithZenith/wolf-algo-beta).
