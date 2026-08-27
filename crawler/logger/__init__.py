import logging
from pathlib import Path

from crawler.config import LOG_DIR

LOG_DIR.mkdir(parents=True, exist_ok=True)


def _configure_logger(name: str, level: int, filename: str, formatter: str):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
        handler.setFormatter(logging.Formatter(formatter))
        logger.addHandler(handler)
    return logger


event_logger = _configure_logger(
    "event_logger",
    logging.INFO,
    "events_history.log",
    "%(asctime)s | %(levelname)s | %(message)s",
)
error_logger = _configure_logger(
    "error_logger", logging.ERROR, "failed_products.csv", "%(asctime)s,%(message)s"
)
success_logger = _configure_logger(
    "success_logger", logging.INFO, "successful_products.csv", "%(asctime)s,%(message)s"
)

for filename, header in (
    ("failed_products.csv", "timestamp,product_id,error_reason\n"),
    ("successful_products.csv", "timestamp,product_id,status\n"),
):
    log_file = LOG_DIR / filename
    if not log_file.exists() or log_file.stat().st_size == 0:
        log_file.write_text(header, encoding="utf-8")
