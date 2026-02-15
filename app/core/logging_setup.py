import logging
from logging.handlers import RotatingFileHandler

from app.config import config


def setup_logging() -> None:
    config.logs_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    app_log_handler = RotatingFileHandler(
        config.logs_dir / "bot.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    app_log_handler.setFormatter(formatter)

    error_log_handler = RotatingFileHandler(
        config.logs_dir / "errors.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    error_log_handler.setLevel(logging.ERROR)
    error_log_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_log_handler)
    root_logger.addHandler(error_log_handler)
