import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from bot.config import get_settings


_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level.upper())

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    for noisy in ("httpx", "httpcore", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
