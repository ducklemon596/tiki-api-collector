from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR = DATA_DIR / "logs"

INPUT_FILE = INPUT_DIR / "products-01.txt"
NOT_FOUND_FILE = LOG_DIR / "404_not_found.log"
EVENT_LOG_FILE = LOG_DIR / "events_history.log"
WRITE_DISK_FILE = LOG_DIR / "write_disk.log"

DELAY = 1.5  # Thời gian nghỉ bình thường
REQUEST_TIMEOUT = 10  # Thời gian chờ tối đa cho mỗi request (giây)
WAF_RETRY_DELAY = 600  # Phạt 10 phút (600s) nếu dính WAF/HTML
MAX_WAF_RETRIES = 3  # Số lần thử lại tối đa cho 1 ID
BATCH_SIZE = 1000  # Số lượng ID mỗi batch
SAVE_INTERVAL = 50  # Flush and fsync append-only checkpoints every 50 terminal records

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://tiki.vn/",
}

HTML_TAG_REGEX = re.compile(r"<[^>]+>")
