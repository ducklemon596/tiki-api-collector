import logging


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
