"""
Wolf Algo — Market Data Feed
==============================
Abstract data feed interface with YFinance and CSV implementations.
"""

import pandas as pd
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import logging

from utils.logger import LogTag, log_event


class DataFeed(ABC):
    """Abstract data feed interface."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        start: str,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV bar data.
        
        Args:
            symbol:    Ticker symbol (e.g. 'SPY', 'ES=F')
            start:     Start date (YYYY-MM-DD)
            end:       End date (YYYY-MM-DD), defaults to today
            timeframe: Bar interval ('1d', '1h', '5m', etc.)
        
        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
            DatetimeIndex
        """
        ...


class YFinanceFeed(DataFeed):
    """
    Yahoo Finance data feed.
    Pulls historical OHLCV data using yfinance.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("wolf_algo.data")

    def get_bars(
        self,
        symbol: str,
        start: str,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        import yfinance as yf

        log_event(
            self.logger, "info", LogTag.DATA,
            f"Fetching {symbol} data from {start} to {end or 'now'} ({timeframe})",
        )

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=timeframe, auto_adjust=True)

        if df.empty:
            log_event(
                self.logger, "warning", LogTag.DATA,
                f"No data returned for {symbol}",
            )
            return pd.DataFrame()

        # Ensure clean column names
        df = df.rename(columns={
            "Open": "Open",
            "High": "High",
            "Low": "Low",
            "Close": "Close",
            "Volume": "Volume",
        })

        # Keep only OHLCV
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)

        log_event(
            self.logger, "info", LogTag.DATA,
            f"Loaded {len(df)} bars for {symbol} ({df.index[0]} → {df.index[-1]})",
        )

        return df


class CSVFeed(DataFeed):
    """
    Local CSV data feed.
    Reads OHLCV data from a CSV file.
    
    Expected CSV format:
        Date,Open,High,Low,Close,Volume
        2020-01-01,100.0,101.5,99.5,101.0,1000000
    """

    def __init__(self, data_dir: str = "data/csv", logger: Optional[logging.Logger] = None):
        self.data_dir = Path(data_dir)
        self.logger = logger or logging.getLogger("wolf_algo.data")

    def get_bars(
        self,
        symbol: str,
        start: str,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        # Look for file named {symbol}.csv
        csv_path = self.data_dir / f"{symbol}.csv"

        if not csv_path.exists():
            log_event(
                self.logger, "error", LogTag.DATA,
                f"CSV file not found: {csv_path}",
            )
            return pd.DataFrame()

        df = pd.read_csv(csv_path, parse_dates=True, index_col=0)

        # Ensure proper column names
        col_map = {c: c.strip().capitalize() for c in df.columns}
        df.rename(columns=col_map, inplace=True)

        # Filter date range
        df.index = pd.to_datetime(df.index)
        if start:
            df = df[df.index >= start]
        if end:
            df = df[df.index <= end]

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)

        log_event(
            self.logger, "info", LogTag.DATA,
            f"Loaded {len(df)} bars from {csv_path.name}",
        )

        return df
