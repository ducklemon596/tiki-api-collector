import logging
from config import (
    EVENT_LOG_FILE,
    NOT_FOUND_FILE,
    WRITE_DISK_FILE,
    LOG_DIR,
)

LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger(name, log_file, level=logging.INFO):
    """Hàm khởi tạo logger ghi ra file"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Tránh duplicate log nếu gọi hàm nhiều lần
    if not logger.handlers:
        # Khởi tạo handler
        handler = logging.FileHandler(log_file, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)

        # Thêm handler vào logger
        logger.addHandler(handler)
    return logger


event_logger = setup_logger("event_logger", EVENT_LOG_FILE)
not_found_logger = setup_logger("not_found_logger", NOT_FOUND_FILE)
write_disk_logger = setup_logger("write_disk_logger", WRITE_DISK_FILE)
