"""
Wolf Algo — Wide-Trailing-Stop & Trend Filter Optimization ($30k+ Profit Target)
===================================================================================
Tests wide ATR trailing stops (5.0 → 8.0 ATR) and macro HMA trend filters (200 → 350)
to achieve profitable compounding returns on SPY historical data (1993–2026).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tabulate import tabulate
from config.settings import load_config, AppConfig, StrategyConfig, AccountConfig, LoggingConfig
from backtest.engine import BacktestEngine
from strategies.wolf_algo import WolfAlgoStrategy
from data.feed import YFinanceFeed
from utils.logger import get_logger


def run_config(bars, symbol, mode, exit_target, risk_pct, use_osc, osc_hard,
               use_trend, trend_period, rr_ratios, sl_buffer, atr_mult_override=None, long_only=True):
    """Run a single backtest config and return results dict."""
    config = load_config()
    strategy_cfg = StrategyConfig(
        sensitivity_mode=mode,
        atr_period=14,
        rr_ratios=rr_ratios,
        pivot_lookback=10,
        sl_buffer_atr_mult=sl_buffer,
    )
    config = AppConfig(
        broker=config.broker,
        risk=config.risk,
        strategy=strategy_cfg,
        execution=config.execution,
        account=AccountConfig(starting_equity=25000.0),
        logging=LoggingConfig(level="WARNING", format="console"),
    )

    strategy = WolfAlgoStrategy(
        sensitivity_mode=mode,
        atr_period=14,
        rr_ratios=rr_ratios,
        pivot_lookback=10,
        sl_buffer_atr_mult=sl_buffer,
    )
    if atr_mult_override is not None:
        strategy.atr_mult = atr_mult_override

    engine = BacktestEngine(
        config=config,
        strategy=strategy,
        use_oscillator_filter=use_osc,
        oscillator_hard_filter=osc_hard,
        exit_target=exit_target,
        use_trend_filter=use_trend,
        trend_filter_period=trend_period,
        risk_per_trade_pct=risk_pct,
        long_only=long_only,
    )
    return engine.run(bars, symbol=symbol)


def main():
    logger = get_logger("sweep", level="WARNING", fmt="console")
    feed = YFinanceFeed(logger=logger)
    symbol = "SPY"
    bars = feed.get_bars(symbol, start="1993-01-01", timeframe="1d")
    print(f"\n📊 Loaded {len(bars)} bars for {symbol}\n")

    # Grid: (label, mode, exit, risk%, osc, osc_hard, trend, trend_period, rr_ratios, sl_buffer, atr_mult, long_only)
    configs = [
        ("Swing, trailing, 2.0%, trend200, atr=5.0",     "swing_trader", "trailing", 2.0, False, False, True, 200, (1.0, 2.0, 3.0), 0.2, 5.0, True),
        ("Swing, trailing, 2.0%, trend250, atr=5.0",     "swing_trader", "trailing", 2.0, False, False, True, 250, (1.0, 2.0, 3.0), 0.2, 5.0, True),
        ("Swing, trailing, 2.0%, trend300, atr=5.0",     "swing_trader", "trailing", 2.0, False, False, True, 300, (1.0, 2.0, 3.0), 0.2, 5.0, True),
        
        # ATR 6.0 - 8.0
        ("Swing, trailing, 2.0%, trend200, atr=6.0",     "swing_trader", "trailing", 2.0, False, False, True, 200, (1.0, 2.0, 3.0), 0.2, 6.0, True),
        ("Swing, trailing, 2.0%, trend250, atr=6.0",     "swing_trader", "trailing", 2.0, False, False, True, 250, (1.0, 2.0, 3.0), 0.2, 6.0, True),
        ("Swing, trailing, 2.0%, trend300, atr=6.0",     "swing_trader", "trailing", 2.0, False, False, True, 300, (1.0, 2.0, 3.0), 0.2, 6.0, True),
        ("Swing, trailing, 2.0%, trend250, atr=7.0",     "swing_trader", "trailing", 2.0, False, False, True, 250, (1.0, 2.0, 3.0), 0.2, 7.0, True),
        ("Swing, trailing, 2.0%, trend300, atr=7.0",     "swing_trader", "trailing", 2.0, False, False, True, 300, (1.0, 2.0, 3.0), 0.2, 7.0, True),

        # Risk scaling at ATR 6.0
        ("Swing, trailing, 2.5%, trend250, atr=6.0",     "swing_trader", "trailing", 2.5, False, False, True, 250, (1.0, 2.0, 3.0), 0.2, 6.0, True),
        ("Swing, trailing, 3.0%, trend250, atr=6.0",     "swing_trader", "trailing", 3.0, False, False, True, 250, (1.0, 2.0, 3.0), 0.2, 6.0, True),
        ("Swing, trailing, 3.5%, trend250, atr=6.0",     "swing_trader", "trailing", 3.5, False, False, True, 250, (1.0, 2.0, 3.0), 0.2, 6.0, True),
        ("Swing, trailing, 2.5%, trend300, atr=7.0",     "swing_trader", "trailing", 2.5, False, False, True, 300, (1.0, 2.0, 3.0), 0.2, 7.0, True),
    ]

    results_table = []

    for idx, config_tuple in enumerate(configs):
        label = config_tuple[0]
        mode, exit_t, risk, osc, osc_h, trend, tp, rr, sl = config_tuple[1:10]
        atr_m = config_tuple[10] if len(config_tuple) > 10 else None
        l_only = config_tuple[11] if len(config_tuple) > 11 else True

        print(f"  [{idx+1}/{len(configs)}] Testing: {label}...")
        try:
            r = run_config(bars, symbol, mode, exit_t, risk, osc, osc_h, trend, tp, rr, sl, atr_m, l_only)
            results_table.append([
                label,
                r["total_trades"],
                f"{r['win_rate_pct']:.1f}%",
                f"{r['profit_factor']:.2f}",
                f"{r['sharpe_ratio']:.2f}",
                f"{r['max_drawdown_pct']:.1f}%",
                f"${r['final_equity']:,.0f}",
                f"{r['total_return_pct']:.1f}%",
            ])
        except Exception as e:
            results_table.append([label, "ERR", "-", "-", "-", "-", "-", str(e)[:30]])

    print(f"\n{'='*110}")
    print(f"  🐺 WIDE ATR & REGIME OPTIMIZATION RESULTS")
    print(f"{'='*110}\n")

    headers = ["Config", "Trades", "Win%", "PF", "Sharpe", "MaxDD", "Final Eq", "Return"]
    print(tabulate(results_table, headers=headers, tablefmt="simple"))
    print()


if __name__ == "__main__":
    main()
