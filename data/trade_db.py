"""
Wolf Algo — Persistent SQLite Trade Audit & History Database
=============================================================
Records all trade executions, entry/exit prices, lot sizes, PnL,
slippage friction, and HMM market regime states into SQLite.
"""

import os
import sys
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path(__file__).parent.parent / "data" / "trade_history.sqlite"


class TradeDatabase:
    """
    Persistent SQLite database manager for trade audit logging and analytics.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initializes database schema if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    sl_price REAL,
                    tp1_price REAL,
                    tp2_price REAL,
                    pnl REAL DEFAULT 0.0,
                    status TEXT NOT NULL,
                    hmm_regime TEXT,
                    spread REAL,
                    notes TEXT
                )
            """)
            conn.commit()

    def record_trade_entry(
        self,
        account_id: str,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        sl_price: float,
        tp1_price: float,
        tp2_price: float,
        hmm_regime: str = "TREND 🚀",
        spread: float = 0.30
    ) -> int:
        """Records a new trade entry into SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_logs (
                    timestamp, account_id, symbol, side, qty, entry_price, sl_price, tp1_price, tp2_price, status, hmm_regime, spread
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.utcnow().isoformat(),
                account_id,
                symbol,
                side,
                qty,
                entry_price,
                sl_price,
                tp1_price,
                tp2_price,
                "OPEN",
                hmm_regime,
                spread
            ))
            conn.commit()
            return cursor.lastrowid

    def update_trade_exit(self, trade_id: int, exit_price: float, pnl: float, status: str = "CLOSED"):
        """Updates trade log with exit price and final realized PnL."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trade_logs
                SET exit_price = ?, pnl = ?, status = ?
                WHERE id = ?
            """, (exit_price, pnl, status, trade_id))
            conn.commit()

    def get_all_trades(self, limit: int = 50) -> List[Dict]:
        """Fetches completed trade logs from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trade_logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]


trade_db = TradeDatabase()


if __name__ == "__main__":
    print("🧪 Initialized Persistent Trade Database at:", DB_PATH)
