"""
Wolf Algo — Backtest CLI Runner
==================================
Usage:
  python -m backtest.run_backtest --equity 4955.18 --daily-loss 149 --symbol SPY
  python -m backtest.run_backtest --equity 4955.18 --daily-loss 149 --symbol GC=F
"""

import argparse
import sys
from pathlib import Path
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import load_config, AppConfig, StrategyConfig, RiskConfig, AccountConfig, LoggingConfig
from backtest.engine import BacktestEngine
from strategies.wolf_algo import WolfAlgoStrategy
from data.feed import YFinanceFeed
from utils.logger import get_logger, LogTag, log_event


def main():
    parser = argparse.ArgumentParser(
        description="Wolf Algo Backtest Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", default="GC=F", help="Ticker symbol (e.g. GC=F, SPY, QQQ)")
    parser.add_argument("--interval", default="15m", choices=["1m", "5m", "15m", "1h", "1d"], help="Bar timeframe interval (default: 15m)")
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--mode", default="scalper", choices=["scalper", "day_trader", "swing_trader"])
    parser.add_argument("--equity", type=float, default=5000.00, help="Starting account equity (default: 5000.00)")
    parser.add_argument("--daily-loss", type=float, default=150.00, help="Hard daily loss limit in $ (default: 150.00)")
    parser.add_argument("--risk-pct", type=float, default=2.5, help="Risk per trade as %% of equity (default: 2.5)")
    parser.add_argument("--exit", default="trailing", choices=["tp1", "tp2", "tp3", "trailing"], help="Exit strategy (default: trailing)")
    parser.add_argument("--long-only", action="store_true", default=False, help="Long-only mode")
    parser.add_argument("--allow-short", action="store_true", default=True, help="Allow short trades")
    parser.add_argument("--no-oscillator", action="store_true", help="Disable oscillator filter")
    parser.add_argument("--soft-oscillator", action="store_true", default=True, help="Use oscillator as soft filter")
    parser.add_argument("--no-trend-filter", action="store_true", help="Disable trend alignment filter")
    parser.add_argument("--trend-period", type=int, default=50, help="Trend filter HMA period (default: 50)")
    parser.add_argument("--atr-mult", type=float, default=2.5, help="ATR trailing stop multiplier (default: 2.5)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])

    args = parser.parse_args()

    config = load_config()

    long_only_flag = args.long_only if args.long_only else (not args.allow_short)

    risk_cfg = RiskConfig(
        max_drawdown_pct=config.risk.max_drawdown_pct,
        max_loss_per_trade_pct=args.risk_pct,
        hard_daily_loss_limit=args.daily_loss,
        max_open_positions=config.risk.max_open_positions,
        require_structural_stop=config.risk.require_structural_stop,
        long_only=long_only_flag,
    )
    strategy_cfg = StrategyConfig(
        sensitivity_mode=args.mode,
        atr_period=config.strategy.atr_period,
        rr_ratios=config.strategy.rr_ratios,
        pivot_lookback=config.strategy.pivot_lookback,
        sl_buffer_atr_mult=config.strategy.sl_buffer_atr_mult,
    )
    account_cfg = AccountConfig(starting_equity=args.equity, currency=config.account.currency)
    logging_cfg = LoggingConfig(level=args.log_level, format="console", file=config.logging.file)
    config = AppConfig(
        broker=config.broker,
        risk=risk_cfg,
        strategy=strategy_cfg,
        execution=config.execution,
        account=account_cfg,
        logging=logging_cfg,
    )

    logger = get_logger("wolf_algo.backtest", level=args.log_level, fmt="console")

    print(f"\n{'='*60}")
    print(f"  🐺 WOLF ALGO BACKTEST — TRADELOCKER ACCOUNT")
    print(f"{'='*60}")
    print(f"  Symbol:           {args.symbol}")
    print(f"  Period:           {args.start} → {args.end or 'present'}")
    print(f"  Mode:             {args.mode}")
    print(f"  Account Equity:   ${args.equity:,.2f}")
    print(f"  Daily Loss Limit: ${args.daily_loss:,.2f}")
    print(f"  Risk per Trade:   {args.risk_pct}% (${args.equity * (args.risk_pct/100):,.2f})")
    print(f"  Exit Target:      {args.exit.upper()}")
    print(f"  ATR Multiplier:   {args.atr_mult}")
    print(f"  Trend Filter:     {'ON (HMA-{})'.format(args.trend_period) if not args.no_trend_filter else 'OFF'}")
    print(f"  Trade Direction:  {'LONG-ONLY' if long_only_flag else 'LONG + SHORT'}")
    print(f"{'='*60}\n")

    feed = YFinanceFeed(logger=logger)
    bars = feed.get_bars(args.symbol, start=args.start, end=args.end, timeframe=args.interval)

    if bars.empty:
        print("❌ No data returned. Check symbol and date range.")
        sys.exit(1)

    print(f"  📊 Loaded {len(bars)} daily bars for {args.symbol}\n")

    strategy = WolfAlgoStrategy(
        sensitivity_mode=args.mode,
        atr_period=config.strategy.atr_period,
        rr_ratios=config.strategy.rr_ratios,
        pivot_lookback=config.strategy.pivot_lookback,
        sl_buffer_atr_mult=config.strategy.sl_buffer_atr_mult,
    )
    if args.atr_mult is not None:
        strategy.atr_mult = args.atr_mult

    engine = BacktestEngine(
        config=config,
        strategy=strategy,
        use_oscillator_filter=not args.no_oscillator,
        oscillator_hard_filter=not args.soft_oscillator,
        exit_target=args.exit,
        use_trend_filter=not args.no_trend_filter,
        trend_filter_period=args.trend_period,
        risk_per_trade_pct=args.risk_pct,
        long_only=long_only_flag,
    )

    results = engine.run(bars, symbol=args.symbol)

    print(f"\n{'='*60}")
    print(f"  📈 PERFORMANCE REPORT — TRADELOCKER ($4,955.18)")
    print(f"{'='*60}\n")

    summary = [
        ["Strategy", results["strategy"]],
        ["Symbol", results["symbol"]],
        ["Starting Equity", f"${results['starting_equity']:,.2f}"],
        ["Final Equity", f"${results['final_equity']:,.2f}"],
        ["Total Return", f"${results['total_return']:,.2f} ({results['total_return_pct']:.2f}%)"],
        ["", ""],
        ["Total Trades", results["total_trades"]],
        ["Winning Trades", results["winning_trades"]],
        ["Losing Trades", results["losing_trades"]],
        ["Win Rate", f"{results['win_rate_pct']:.2f}%"],
        ["", ""],
        ["Profit Factor", f"{results['profit_factor']:.2f}"],
        ["Sharpe Ratio", f"{results['sharpe_ratio']:.2f}"],
        ["Max Drawdown", f"{results['max_drawdown_pct']:.2f}%"],
    ]

    print(tabulate(summary, tablefmt="simple", colalign=("right", "left")))

    trade_log = results["trade_log"]
    if trade_log:
        print(f"\n{'='*60}")
        print(f"  📋 LAST 20 TRADES")
        print(f"{'='*60}\n")

        recent = trade_log[-20:]
        trade_table = []
        for t in recent:
            pnl_str = f"${t['pnl']:,.2f}"
            emoji = "✅" if t["pnl"] >= 0 else "❌"
            trade_table.append([
                t.get("entry_time", "")[:10] if t.get("entry_time") else "",
                t["direction"],
                f"${t['entry_price']:,.2f}",
                f"${t['exit_price']:,.2f}",
                f"${t['stop_loss']:,.2f}",
                t["quantity"],
                f"{emoji} {pnl_str}",
            ])

        headers = ["Date", "Dir", "Entry", "Exit", "SL", "Qty", "PnL"]
        print(tabulate(trade_table, headers=headers, tablefmt="simple"))

    print(f"\n{'='*60}")
    print(f"  🐺 TradeLocker Backtest Complete.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
