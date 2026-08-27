"""CLI entry point for synchronous and asynchronous crawlers."""

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

from crawler import config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl Tiki product details")
    parser.add_argument(
        "--mode",
        choices=("sync", "async"),
        default="sync",
        help="Crawler mode (default: sync)",
    )
    parser.add_argument("--input", type=Path, default=config.INPUT_FILE)
    parser.add_argument("--output", type=Path, default=config.OUTPUT_DIR)
    parser.add_argument("--batch-size", type=int, default=config.BATCH_SIZE)
    parser.add_argument("--timeout", type=float, default=config.REQUEST_TIMEOUT)
    parser.add_argument("--retries", type=int, default=config.MAX_RETRIES)
    parser.add_argument(
        "--delay",
        type=float,
        default=config.DELAY_BETWEEN_REQUESTS,
        help="Delay between sync requests in seconds",
    )
    parser.add_argument("--concurrency", type=int, default=config.CONCURRENCY_LIMIT)
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=config.API_RATE_LIMIT,
        help="Maximum async requests per second",
    )
    parser.add_argument("--proxy", default=config.PROXY)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    positive = {
        "batch-size": args.batch_size,
        "timeout": args.timeout,
        "retries": args.retries,
        "concurrency": args.concurrency,
        "rate-limit": args.rate_limit,
    }
    if any(value <= 0 for value in positive.values()):
        raise ValueError(
            "batch-size, timeout, retries, concurrency và rate-limit phải > 0"
        )
    if args.delay < 0:
        raise ValueError("delay phải >= 0")
    if not args.input.is_file():
        raise FileNotFoundError(f"Không tìm thấy file input: {args.input}")


def apply_runtime_config(args: argparse.Namespace) -> None:
    """Update the shared config values used by both crawler implementations."""
    config.INPUT_FILE = args.input
    config.OUTPUT_DIR = args.output
    config.BATCH_SIZE = args.batch_size
    config.REQUEST_TIMEOUT = args.timeout
    config.MAX_RETRIES = args.retries
    config.DELAY_BETWEEN_REQUESTS = args.delay
    config.CONCURRENCY_LIMIT = args.concurrency
    config.API_RATE_LIMIT = args.rate_limit
    config.PROXY = args.proxy

    # Crawler modules import these names directly, so keep their runtime values in sync.
    from crawler import async_crawler, sync_crawler

    for module in (async_crawler, sync_crawler):
        module.INPUT_FILE = config.INPUT_FILE
        module.OUTPUT_DIR = config.OUTPUT_DIR
        module.BATCH_SIZE = config.BATCH_SIZE
        module.REQUEST_TIMEOUT = config.REQUEST_TIMEOUT
        module.MAX_RETRIES = config.MAX_RETRIES
        module.PROXY = config.PROXY

    async_crawler.CONCURRENCY_LIMIT = config.CONCURRENCY_LIMIT
    async_crawler.API_RATE_LIMIT = config.API_RATE_LIMIT
    sync_crawler.DELAY_BETWEEN_REQUESTS = config.DELAY_BETWEEN_REQUESTS


def run(args: argparse.Namespace) -> Any:
    validate_args(args)
    apply_runtime_config(args)

    if args.mode == "sync":
        from crawler.sync_crawler import main as sync_main

        return sync_main()

    from crawler.async_crawler import main as async_main

    return asyncio.run(async_main())


def main() -> None:
    args = parse_args()
    try:
        run(args)
    except (FileNotFoundError, ValueError) as error:
        raise SystemExit(f"Lỗi: {error}") from error


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
