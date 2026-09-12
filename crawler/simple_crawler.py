import argparse
import random
import time
from pathlib import Path

from config import (
    BATCH_SIZE,
    DATA_DIR,
    INPUT_DIR,
    INPUT_FILE,
    MAX_WAF_RETRIES,
    REQUEST_TIMEOUT,
    SAVE_INTERVAL,
    WAF_RETRY_DELAY,
)
from logger import setup_logger
from utils import BatchCheckpoint, SeleniumTikiClient, fetch_product_data, load_and_batch_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-batch", type=int, default=1)
    parser.add_argument("--end-batch", type=int, default=None)
    parser.add_argument("--worker-id", default="worker-01")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Isolated directory for this worker's checkpoints, final output, and logs.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=MAX_WAF_RETRIES,
        help="Number of retries for network, WAF, or malformed-response failures.",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=WAF_RETRY_DELAY,
        help="Initial retry delay in seconds; it doubles after each failed attempt.",
    )
    parser.add_argument("--delay-min", type=float, default=0.0)
    parser.add_argument("--delay-max", type=float, default=0.0)
    args = parser.parse_args()
    if args.delay_min < 0 or args.delay_max < args.delay_min:
        parser.error("Require 0 <= --delay-min <= --delay-max")
    if args.max_retries < 0 or args.retry_delay < 0:
        parser.error("Require --max-retries and --retry-delay to be non-negative")

    run_dir = args.run_dir or DATA_DIR / "runs" / args.worker_id
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    event_logger = setup_logger(
        f"event_logger_{args.worker_id}", log_dir / "events.log"
    )
    not_found_logger = setup_logger(
        f"not_found_logger_{args.worker_id}", log_dir / "not_found.log"
    )

    batches, total_ids = load_and_batch_ids(INPUT_FILE, BATCH_SIZE)
    if not batches:
        print(f"No valid IDs found at: {INPUT_FILE}")
        return

    end_batch = min(args.end_batch or len(batches), len(batches))
    start_batch = max(args.start_batch, 1)
    print(f"Total IDs: {total_ids:,}; batches: {start_batch}-{end_batch}")

    client = SeleniumTikiClient(timeout=REQUEST_TIMEOUT)
    try:
        event_logger.info("Opening Tiki in the persistent Selenium browser")
        client.open_tiki()
        for batch_num in range(start_batch, end_batch + 1):
            assigned_ids = batches[batch_num - 1]
            checkpoint = BatchCheckpoint(
                run_dir, batch_num, sync_interval=SAVE_INTERVAL
            )
            if checkpoint.finalized:
                event_logger.info("Batch %04d already finalized; skipping", batch_num)
                continue

            existing_products, completed_ids = checkpoint.load_completed()
            pending_ids = [
                product_id
                for product_id in assigned_ids
                if product_id not in completed_ids
            ]
            success_count = len(existing_products)
            not_found_count = len(completed_ids) - success_count
            event_logger.info(
                "Starting batch %04d: %d pending, %d completed",
                batch_num,
                len(pending_ids),
                len(completed_ids),
            )

            checkpoint.open()
            try:
                for product_id in pending_ids:
                    for attempt in range(args.max_retries + 1):
                        product, not_found_status = fetch_product_data(
                            client=client,
                            product_id=product_id,
                            batch_num=batch_num,
                            event_logger=event_logger,
                            not_found_logger=not_found_logger,
                        )
                        if product is not None or not_found_status is not None:
                            break

                        if attempt == args.max_retries:
                            event_logger.error(
                                "product_id=%s exhausted %d retry attempts; leaving it uncheckpointed for a later run",
                                product_id,
                                args.max_retries,
                            )
                            break

                        retry_delay = args.retry_delay * (2**attempt)
                        event_logger.warning(
                            "product_id=%s retrying attempt %d/%d after %.1fs",
                            product_id,
                            attempt + 1,
                            args.max_retries,
                            retry_delay,
                        )
                        if retry_delay:
                            time.sleep(retry_delay)
                    if product is not None:
                        success_count += 1
                        synced = checkpoint.record_success(product)
                    elif not_found_status is not None:
                        not_found_count += 1
                        synced = checkpoint.record_not_found(
                            product_id, not_found_status
                        )
                    else:
                        # Retryable errors are deliberately not terminal checkpoint records.
                        synced = False
                    if synced:
                        checkpoint.write_state(
                            args.worker_id, success_count, not_found_count
                        )
                    time.sleep(random.uniform(args.delay_min, args.delay_max))

                checkpoint.write_state(args.worker_id, success_count, not_found_count)
                final_path = checkpoint.finalize()
                event_logger.info("Finalized batch %04d at %s", batch_num, final_path)
            finally:
                checkpoint.close()

    finally:
        event_logger.info("Selenium session summary: %s", client.summary())
        event_logger.info("Closing persistent Selenium browser")
        client.close()

    print("Crawl complete.")


if __name__ == "__main__":
    main()
