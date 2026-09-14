"""Stable application defaults for the supported two-browser crawler."""

from pathlib import Path
import re

# Repository-level defaults. Runtime output layout is derived from ``--run-dir``.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT_FILE = DATA_DIR / "input" / "products-01.txt"
DEFAULT_RUN_DIR = DATA_DIR / "runs" / "default-crawl"

# Two-browser crawler behavior.
BROWSER_COUNT = 2
DEFAULT_BROWSER_CONCURRENCY = 4
ALLOWED_BROWSER_CONCURRENCY = (4, 8)
DEFAULT_SELENIUM_CALL_SIZE = 50
DEFAULT_START_BATCH = 1
DEFAULT_END_BATCH = 200
REQUEST_TIMEOUT_SECONDS = 10
INPUT_BATCH_SIZE = 1_000
CHECKPOINT_SYNC_INTERVAL = 100
MAX_CONSECUTIVE_BROWSER_ERRORS = 3

# Monitor defaults.
DEFAULT_MONITOR_MILESTONE = 10_000
DEFAULT_MONITOR_INTERVAL_SECONDS = 15.0

HTML_TAG_REGEX = re.compile(r"<[^>]+>")
