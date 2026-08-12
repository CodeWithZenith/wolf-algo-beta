# ============================================
# Wolf Algo — Docker Container Definition
# ============================================

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for scientific libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt-get/lists/*

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create directory for logs and local data persistence
RUN mkdir -p logs data/csv

# Default entry point runs the backtest runner
ENTRYPOINT ["python", "-m", "backtest.run_backtest"]
CMD ["--symbol", "SPY", "--start", "1993-01-01", "--mode", "swing_trader", "--exit", "trailing", "--risk-pct", "3.5", "--atr-mult", "6.0", "--trend-period", "250"]
