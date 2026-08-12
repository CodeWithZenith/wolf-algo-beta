"""
Wolf Algo — Configuration Loader
=================================
Reads environment variables (.env) and default_config.yaml,
merges them into a validated AppConfig dataclass.
"""

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Dataclass hierarchy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BrokerConfig:
    api_key: str = ""
    api_secret: str = ""
    api_url: str = "https://demo.tradovateapi.com/v1"
    account_id: str = ""
    timeout_seconds: int = 10
    use_mock: bool = True


@dataclass(frozen=True)
class RiskConfig:
    max_drawdown_pct: float = 25.0
    max_loss_per_trade_pct: float = 3.0
    hard_daily_loss_limit: float = 1500.0
    max_open_positions: int = 3
    require_structural_stop: bool = True
    long_only: bool = True


@dataclass(frozen=True)
class StrategyConfig:
    sensitivity_mode: str = "day_trader"
    atr_period: int = 14
    rr_ratios: tuple = (1.0, 2.0, 3.0)
    pivot_lookback: int = 10
    sl_buffer_atr_mult: float = 0.2


@dataclass(frozen=True)
class ExecutionConfig:
    slippage_ticks: int = 1
    commission_per_side: float = 2.50
    default_order_type: str = "MARKET"


@dataclass(frozen=True)
class AccountConfig:
    starting_equity: float = 25000.0
    currency: str = "USD"


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    format: str = "json"
    file: str = "logs/wolf_algo.log"


@dataclass(frozen=True)
class AppConfig:
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    account: AccountConfig = field(default_factory=AccountConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _resolve_config_path() -> Path:
    """Find default_config.yaml relative to this file."""
    return Path(__file__).parent / "default_config.yaml"


def load_config(env_path: Optional[str] = None) -> AppConfig:
    """
    Load configuration in priority order:
      1. Environment variables (.env)  — highest priority
      2. default_config.yaml           — base defaults
    
    Returns a frozen AppConfig instance.
    """
    # Load .env if it exists
    project_root = Path(__file__).parent.parent
    dotenv_path = Path(env_path) if env_path else project_root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)

    # Load YAML defaults
    yaml_path = _resolve_config_path()
    if yaml_path.exists():
        with open(yaml_path, "r") as f:
            yml = yaml.safe_load(f) or {}
    else:
        yml = {}

    # Merge: env vars take precedence over YAML
    broker_yml = yml.get("broker", {})
    risk_yml = yml.get("risk", {})
    strategy_yml = yml.get("strategy", {})
    exec_yml = yml.get("execution", {})
    account_yml = yml.get("account", {})
    log_yml = yml.get("logging", {})

    broker = BrokerConfig(
        api_key=os.getenv("BROKER_API_KEY", broker_yml.get("api_key", "")),
        api_secret=os.getenv("BROKER_API_SECRET", broker_yml.get("api_secret", "")),
        api_url=os.getenv("BROKER_API_URL", broker_yml.get("api_url", "https://demo.tradovateapi.com/v1")),
        account_id=os.getenv("ACCOUNT_ID", broker_yml.get("account_id", "")),
        timeout_seconds=broker_yml.get("timeout_seconds", 10),
        use_mock=broker_yml.get("use_mock", True),
    )

    def _get_float_env(var_name: str, fallback: float) -> float:
        val = os.getenv(var_name)
        if val is not None and val.strip() != "":
            try:
                return float(val)
            except ValueError:
                pass
        return fallback

    risk = RiskConfig(
        max_drawdown_pct=_get_float_env("MAX_DRAWDOWN_PCT", risk_yml.get("max_drawdown_pct", 25.0)),
        max_loss_per_trade_pct=_get_float_env("MAX_LOSS_PER_TRADE_PCT", risk_yml.get("max_loss_per_trade_pct", 3.0)),
        hard_daily_loss_limit=_get_float_env("HARD_DAILY_LOSS_LIMIT", risk_yml.get("hard_daily_loss_limit", 1500.0)),
        max_open_positions=risk_yml.get("max_open_positions", 3),
        require_structural_stop=risk_yml.get("require_structural_stop", True),
    )

    rr_raw = strategy_yml.get("rr_ratios", [1.0, 2.0, 3.0])
    strategy = StrategyConfig(
        sensitivity_mode=strategy_yml.get("sensitivity_mode", "day_trader"),
        atr_period=strategy_yml.get("atr_period", 14),
        rr_ratios=tuple(rr_raw) if isinstance(rr_raw, list) else rr_raw,
        pivot_lookback=strategy_yml.get("pivot_lookback", 10),
        sl_buffer_atr_mult=strategy_yml.get("sl_buffer_atr_mult", 0.2),
    )

    execution = ExecutionConfig(
        slippage_ticks=exec_yml.get("slippage_ticks", 1),
        commission_per_side=exec_yml.get("commission_per_side", 2.50),
        default_order_type=exec_yml.get("default_order_type", "MARKET"),
    )

    account = AccountConfig(
        starting_equity=account_yml.get("starting_equity", 25000.0),
        currency=account_yml.get("currency", "USD"),
    )

    logging_cfg = LoggingConfig(
        level=os.getenv("LOG_LEVEL", log_yml.get("level", "INFO")),
        format=os.getenv("LOG_FORMAT", log_yml.get("format", "json")),
        file=log_yml.get("file", "logs/wolf_algo.log"),
    )

    return AppConfig(
        broker=broker,
        risk=risk,
        strategy=strategy,
        execution=execution,
        account=account,
        logging=logging_cfg,
    )
