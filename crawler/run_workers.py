"""Launch multiple isolated crawler workers over contiguous batch ranges."""

import argparse
import subprocess
import sys
from pathlib import Path

from config import BATCH_SIZE, DATA_DIR, INPUT_FILE, PROJECT_ROOT
from utils import load_and_batch_ids


def split_batch_ranges(total_batches: int, worker_count: int) -> list[tuple[int, int]]:
    """Split 1-based batch numbers into balanced, consecutive ranges."""
    if worker_count < 1:
        raise ValueError("worker_count must be at least 1")
    if worker_count > total_batches:
        raise ValueError("worker_count cannot exceed the number of batches")

    base_size, remainder = divmod(total_batches, worker_count)
    ranges = []
    start = 1
    for index in range(worker_count):
        size = base_size + (1 if index < remainder else 0)
        end = start + size - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


def terminate_children(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start concurrent crawler processes with isolated run directories."
    )
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument(
        "--worker-domain",
        default="thienquang050906.workers.dev",
        help="Worker host suffix; endpoints are tiki-crawler-01 through tiki-crawler-NN.",
    )
    parser.add_argument("--run-root", type=Path, default=DATA_DIR / "runs")
    parser.add_argument(
        "--detach",
        action="store_true",
        help="Start workers and return immediately instead of monitoring them.",
    )
    args = parser.parse_args()

    batches, total_ids = load_and_batch_ids(INPUT_FILE, BATCH_SIZE)
    if not batches:
        raise SystemExit(f"No valid IDs found at: {INPUT_FILE}")

    ranges = split_batch_ranges(len(batches), args.workers)
    crawler_script = Path(__file__).with_name("simple_crawler.py")
    processes: list[subprocess.Popen] = []

    try:
        for worker_number, (start_batch, end_batch) in enumerate(ranges, start=1):
            worker_id = f"worker-{worker_number:02d}"
            worker_url = f"tiki-crawler-{worker_number:02d}.{args.worker_domain}"
            log_dir = args.run_root / worker_id / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            stdout = open(log_dir / "launcher_stdout.log", "ab")
            stderr = open(log_dir / "launcher_stderr.log", "ab")
            command = [
                sys.executable,
                str(crawler_script),
                "--worker-id",
                worker_id,
                "--run-dir",
                str(args.run_root / worker_id),
                "--start-batch",
                str(start_batch),
                "--end-batch",
                str(end_batch),
                "--cloudflare-worker-url",
                worker_url,
            ]
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=stdout,
                stderr=stderr,
            )
            # Popen duplicates the file handles; the parent can close its copies.
            stdout.close()
            stderr.close()
            processes.append(process)
            print(
                f"Started {worker_id} (pid {process.pid}): "
                f"batches {start_batch}-{end_batch}, {worker_url}"
            )
    except Exception:
        terminate_children(processes)
        raise

    print(f"Launched {len(processes)} workers for {total_ids:,} IDs.")
    if args.detach:
        return

    try:
        exit_codes = [process.wait() for process in processes]
    except KeyboardInterrupt:
        print("Stopping workers; append-only checkpoints are safe to resume.")
        terminate_children(processes)
        raise SystemExit(130)

    failed = [process.pid for process, code in zip(processes, exit_codes) if code != 0]
    if failed:
        raise SystemExit(f"Workers failed: {failed}")


if __name__ == "__main__":
    main()
