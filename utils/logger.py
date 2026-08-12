"""
Wolf Algo — Structured Logger
==============================
JSON or console-formatted logging with domain-specific tags
for tracking every state change, order, fill, and rejection.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


class LogTag(str, Enum):
    """Domain tags for structured log filtering."""
    SYSTEM       = "SYSTEM"
    SIGNAL       = "SIGNAL"
    ORDER        = "ORDER"
    FILL         = "FILL"
    REJECT       = "REJECT"
    RISK         = "RISK"
    STATE_CHANGE = "STATE_CHANGE"
    DATA         = "DATA"
    BACKTEST     = "BACKTEST"
    ERROR        = "ERROR"


class JsonFormatter(logging.Formatter):
    """Emits each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "tag": getattr(record, "tag", LogTag.SYSTEM.value),
            "msg": record.getMessage(),
        }
        # Attach extra payload if present
        payload = getattr(record, "payload", None)
        if payload:
            entry["payload"] = payload
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = str(record.exc_info[1])
        return json.dumps(entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Clean, color-coded console output."""

    COLORS = {
        "DEBUG":    "\033[90m",
        "INFO":     "\033[36m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[1;31m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        tag = getattr(record, "tag", LogTag.SYSTEM.value)
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        msg = record.getMessage()
        base = f"{color}{ts} [{record.levelname:<7}] [{tag:<12}]{self.RESET} {msg}"
        payload = getattr(record, "payload", None)
        if payload:
            base += f"  | {json.dumps(payload, default=str)}"
        return base


def get_logger(
    name: str = "wolf_algo",
    level: str = "INFO",
    fmt: str = "json",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Create or retrieve a configured logger.

    Args:
        name:     Logger name
        level:    Logging level (DEBUG, INFO, WARNING, ERROR)
        fmt:      'json' for structured JSON, 'console' for human-readable
        log_file: Optional path for rotating file output
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    # Formatter
    formatter = JsonFormatter() if fmt == "json" else ConsoleFormatter()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path))
        file_handler.setFormatter(JsonFormatter())  # Always JSON for files
        logger.addHandler(file_handler)

    return logger


def log_event(
    logger: logging.Logger,
    level: str,
    tag: LogTag,
    message: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Convenience function for tagged, structured log emission.

    Args:
        logger:  Logger instance
        level:   'info', 'warning', 'error', 'debug'
        tag:     LogTag enum value
        message: Human-readable message
        payload: Optional dict with structured data
    """
    log_fn = getattr(logger, level.lower(), logger.info)
    extra = {"tag": tag.value, "payload": payload}
    log_fn(message, extra=extra)
