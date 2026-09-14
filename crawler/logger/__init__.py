"""File-logger setup shared by browser workers and aggregate reporting."""

import logging
from pathlib import Path


def setup_logger(
    name: str, log_file: Path, level: int = logging.INFO
) -> logging.Logger:
    """Create or reuse a named UTF-8 file logger.

    Args:
        name: Stable logger name used to avoid adding duplicate handlers.
        log_file: Destination log file for this browser or aggregate run.
        level: Minimum logging level to write.

    Returns:
        The configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
