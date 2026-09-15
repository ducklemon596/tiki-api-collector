"""Stable defaults for the crawler and controlled browser-count benchmarks."""

from pathlib import Path
import re

# Repository-level defaults. Runtime output layout is derived from ``--run-dir``.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT_FILE = DATA_DIR / "input" / "products-01.txt"
DEFAULT_RUN_DIR = DATA_DIR / "runs" / "default-crawl"
# Optional local ChromeDriver override. Selenium Manager is used when absent.
CHROMEDRIVER_PATH = Path(r"C:\tools\chromedriver-win64\chromedriver.exe")

# Default crawler behavior; four browsers are allowed for controlled benchmarks.
BROWSER_COUNT = 2
ALLOWED_BROWSER_COUNTS = (2, 4)
DEFAULT_BROWSER_CONCURRENCY = 4
ALLOWED_BROWSER_CONCURRENCY = (4, 8)
DEFAULT_SELENIUM_CALL_SIZE = 50
DEFAULT_START_BATCH = 1
DEFAULT_END_BATCH = 200
REQUEST_TIMEOUT_SECONDS = 10
INPUT_BATCH_SIZE = 1_000
CHECKPOINT_SYNC_INTERVAL = 100
MAX_CONSECUTIVE_BROWSER_ERRORS = 3
# Short retry policy for timeout and browser-transport failures only.
MAX_RETRY_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 1.0
# WAF/challenge responses receive a longer cooldown than transport failures.
WAF_RETRY_DELAYS_SECONDS = (300.0, 600.0, 1_200.0)

# Monitor defaults.
DEFAULT_MONITOR_MILESTONE = 10_000
DEFAULT_MONITOR_INTERVAL_SECONDS = 15.0

HTML_TAG_REGEX = re.compile(r"<[^>]+>")
