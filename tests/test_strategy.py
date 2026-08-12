"""
Wolf Algo — Test Suite: Strategy Signal Generation
=====================================================
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest
from strategies.wolf_algo import WolfAlgoStrategy
from strategies.wolf_oscillator import WolfOscillator
from risk.models import Direction
from utils.helpers import hull_moving_average, calculate_atr, crossover, crossunder


# ── Fixtures ──

@pytest.fixture
def sample_bars():
    """Generate 200 bars of synthetic trending data."""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="D")

    # Trending up then down
    trend_up = np.linspace(100, 130, n // 2)
    trend_down = np.linspace(130, 105, n // 2)
    close = np.concatenate([trend_up, trend_down])

    # Add some noise
    noise = np.random.randn(n) * 1.5
    close = close + noise

    high = close + np.abs(np.random.randn(n)) * 1.0
    low = close - np.abs(np.random.randn(n)) * 1.0
    open_price = close + np.random.randn(n) * 0.5
    volume = np.random.randint(100000, 5000000, n)

    return pd.DataFrame({
        "Open": open_price,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)


# ── HMA Tests ──

class TestHMA:
    def test_hma_returns_series(self, sample_bars):
        hma = hull_moving_average(sample_bars["Close"], 13)
        assert isinstance(hma, pd.Series)
        assert len(hma) == len(sample_bars)

    def test_hma_first_values_nan(self, sample_bars):
        hma = hull_moving_average(sample_bars["Close"], 13)
        # First few values should be NaN due to lookback
        assert pd.isna(hma.iloc[0])

    def test_hma_lags_less_than_sma(self, sample_bars):
        """HMA should respond faster than a simple SMA of the same period."""
        period = 13
        hma = hull_moving_average(sample_bars["Close"], period)
        sma = sample_bars["Close"].rolling(period).mean()

        # Compare variance of difference from close — HMA should be closer
        valid = ~pd.isna(hma) & ~pd.isna(sma)
        hma_diff = (sample_bars["Close"][valid] - hma[valid]).std()
        sma_diff = (sample_bars["Close"][valid] - sma[valid]).std()
        assert hma_diff < sma_diff


# ── ATR Tests ──

class TestATR:
    def test_atr_positive(self, sample_bars):
        atr = calculate_atr(sample_bars["High"], sample_bars["Low"], sample_bars["Close"], 14)
        valid_atr = atr.dropna()
        assert (valid_atr > 0).all()

    def test_atr_length(self, sample_bars):
        atr = calculate_atr(sample_bars["High"], sample_bars["Low"], sample_bars["Close"], 14)
        assert len(atr) == len(sample_bars)


# ── Crossover Tests ──

class TestCrossover:
    def test_crossover_detection(self):
        a = pd.Series([1, 2, 3, 2, 1, 2, 3])
        b = pd.Series([2, 2, 2, 2, 2, 2, 2])
        cross = crossover(a, b)
        # a crosses above b between index 1→2
        assert cross.iloc[2] == True
        assert cross.iloc[0] == False

    def test_crossunder_detection(self):
        a = pd.Series([3, 2, 1, 2, 3, 2, 1])
        b = pd.Series([2, 2, 2, 2, 2, 2, 2])
        cross = crossunder(a, b)
        # a crosses below b between index 1→2
        assert cross.iloc[2] == True


# ── Wolf Algo Strategy Tests ──

class TestWolfAlgoStrategy:
    def test_warmup_period(self):
        strategy = WolfAlgoStrategy(sensitivity_mode="day_trader")
        assert strategy.warmup_period() > 50

    def test_evaluate_returns_signal(self, sample_bars):
        strategy = WolfAlgoStrategy(sensitivity_mode="day_trader")
        signal = strategy.evaluate(sample_bars, symbol="TEST")
        assert signal.symbol == "TEST"
        assert signal.direction in (Direction.LONG, Direction.SHORT, Direction.FLAT)

    def test_insufficient_bars_returns_flat(self):
        strategy = WolfAlgoStrategy(sensitivity_mode="day_trader")
        short_bars = pd.DataFrame({
            "Open": [100], "High": [101], "Low": [99],
            "Close": [100.5], "Volume": [1000],
        }, index=pd.date_range("2020-01-01", periods=1))
        signal = strategy.evaluate(short_bars, symbol="TEST")
        assert signal.direction == Direction.FLAT

    def test_compute_indicators_adds_columns(self, sample_bars):
        strategy = WolfAlgoStrategy()
        df = strategy.compute_indicators(sample_bars)
        expected_cols = ["Cloud1", "Cloud2", "Cloud3", "Cloud4",
                         "TrendDir", "TrailStop", "BuySignal", "SellSignal"]
        for col in expected_cols:
            assert col in df.columns

    def test_sensitivity_modes(self, sample_bars):
        """All sensitivity modes should produce valid signals."""
        for mode in ["scalper", "day_trader", "swing_trader"]:
            strategy = WolfAlgoStrategy(sensitivity_mode=mode)
            signal = strategy.evaluate(sample_bars, symbol="TEST")
            assert signal.direction in (Direction.LONG, Direction.SHORT, Direction.FLAT)

    def test_entry_has_stop_loss(self, sample_bars):
        """If strategy returns an entry signal, it must have a stop price."""
        strategy = WolfAlgoStrategy(sensitivity_mode="day_trader")
        # Evaluate on enough bars to potentially generate a signal
        signal = strategy.evaluate(sample_bars, symbol="TEST")
        if signal.is_entry:
            assert signal.stop_price > 0
            assert len(signal.tp_levels) > 0


# ── Wolf Oscillator Tests ──

class TestWolfOscillator:
    def test_compute_adds_columns(self, sample_bars):
        osc = WolfOscillator()
        df = osc.compute(sample_bars)
        assert "Wave1" in df.columns
        assert "Wave2" in df.columns
        assert "MoneyFlow" in df.columns
        assert "BullConfluence" in df.columns
        assert "BearConfluence" in df.columns

    def test_evaluate_bar_returns_state(self, sample_bars):
        osc = WolfOscillator()
        state = osc.evaluate_bar(sample_bars)
        assert isinstance(state.wave1, float)
        assert isinstance(state.bull_confluence, bool)
        assert -1.0 <= state.confluence_strength <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
