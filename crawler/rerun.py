"""Retry structured not-found/error IDs through the existing crawl command."""

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Sequence
from unittest.mock import patch

PACKAGE_DIRECTORY = str(Path(__file__).resolve().parent)
if PACKAGE_DIRECTORY not in sys.path:
    sys.path.insert(0, PACKAGE_DIRECTORY)

import ujson as json

import execution.orchestration as orchestration
from config import (
    ALLOWED_BROWSER_CONCURRENCY,
    DEFAULT_BROWSER_CONCURRENCY,
    DEFAULT_SELENIUM_CALL_SIZE,
    INPUT_BATCH_SIZE,
)
from main import run_crawl_command
from persistence.checkpoint import write_json_atomically
from persistence.paths import RunPaths


@dataclass(frozen=True)
class RerunSelection:
    """The fixed IDs and source counts for one resumable rerun."""

    ids: list[int]
    not_found_count: int
    error_count: int
    duplicates_removed: int


def _read_ids(
    paths: list[Path], classification: str | None = None, statuses: tuple[int, ...] = ()
) -> list[int]:
    """Read valid positive IDs from JSONL files without changing them."""
    ids: list[int] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as source:
            for line in source:
                try:
                    record = json.loads(line)
                    product_id = int(record["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                if product_id <= 0 or (
                    classification is not None and record.get("classification") != classification
                ) or (
                    statuses and record.get("status") not in statuses
                ):
                    continue
                ids.append(product_id)
    return ids


def collect_selection(source_run: Path) -> RerunSelection:
    """Collect unique source IDs in deterministic not-found-then-error order."""
    if not source_run.is_dir():
        raise FileNotFoundError(f"Source run directory does not exist: {source_run}")
    workers = source_run / "workers"
    not_found = _read_ids(
        sorted(workers.glob("browser-*/checkpoints/not_found/not_found_batch_*.jsonl")),
        statuses=(404, 410),
    )
    errors = _read_ids(
        sorted(workers.glob("browser-*/metrics/errors.jsonl")), classification="error"
    )
    ids = list(dict.fromkeys([*not_found, *errors]))
    return RerunSelection(
        ids=ids,
        not_found_count=len(set(not_found)),
        error_count=len(set(errors)),
        duplicates_removed=len(not_found) + len(errors) - len(ids),
    )


def load_or_create_selection(source_run: Path, run_dir: Path) -> RerunSelection:
    """Freeze a source selection once so the destination run resumes safely."""
    metadata_path = run_dir / "rerun_metadata.json"
    source_name = str(source_run.resolve())
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_run") != source_name:
            raise ValueError("Destination run belongs to a different source run")
        return RerunSelection(
            ids=metadata["ids"],
            not_found_count=metadata["not_found_count"],
            error_count=metadata["error_count"],
            duplicates_removed=metadata["duplicates_removed"],
        )

    selection = collect_selection(source_run)
    write_json_atomically(
        metadata_path,
        {
            "source_run": source_name,
            "created_at": datetime.now(UTC).isoformat(),
            "selected_classifications": ["not-found", "error"],
            "ids": selection.ids,
            "not_found_count": selection.not_found_count,
            "error_count": selection.error_count,
            "duplicates_removed": selection.duplicates_removed,
        },
    )
    return selection


def _checkpoint_ids(run_dir: Path, kind: str) -> set[int]:
    """Read terminal IDs from the destination run's JSONL checkpoints."""
    return set(
        _read_ids(sorted(run_dir.glob(f"workers/browser-*/checkpoints/{kind}/*.jsonl")))
    )


def write_summary(run_dir: Path, source_run: Path, selection: RerunSelection) -> dict[str, object]:
    """Write a compact recovered/still-unfinished summary for the rerun."""
    selected = set(selection.ids)
    successes = _checkpoint_ids(run_dir, "success") & selected
    not_found = _checkpoint_ids(run_dir, "not_found") & selected
    aggregate_path = RunPaths(run_dir).summary
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8")) if aggregate_path.exists() else {}
    summary = {
        "source_run": str(source_run.resolve()),
        "selected_ids": len(selected),
        "source_not_found_ids": selection.not_found_count,
        "source_error_ids": selection.error_count,
        "recovered_successes": len(successes),
        "remaining_not_found": len(not_found),
        "remaining_unfinished_or_error": len(selected - successes - not_found),
        "browser_error_count": aggregate.get("browser_error_count", 0),
        "waf_count": aggregate.get("waf_count", 0),
        "stop_reason": aggregate.get("stop_reason"),
    }
    write_json_atomically(run_dir / "rerun_summary.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> None:
    """Run or resume selected IDs through the unchanged normal crawl pipeline."""
    parser = argparse.ArgumentParser(description="Retry prior not-found/error IDs")
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--selenium-call-size", type=int, default=DEFAULT_SELENIUM_CALL_SIZE)
    parser.add_argument("--concurrency-per-browser", choices=ALLOWED_BROWSER_CONCURRENCY, type=int, default=DEFAULT_BROWSER_CONCURRENCY)
    args = parser.parse_args(argv)
    if args.source_run.resolve() == args.run_dir.resolve():
        parser.error("--source-run and --run-dir must be different")
    if args.selenium_call_size < 1:
        parser.error("Require --selenium-call-size to be at least 1")

    args.run_dir.mkdir(parents=True, exist_ok=True)
    selection = load_or_create_selection(args.source_run, args.run_dir)
    if not selection.ids:
        parser.error("No structured not-found or error IDs were found in the source run")
    input_path = args.run_dir / "rerun_ids.txt"
    input_path.write_text("".join(f"{product_id}\n" for product_id in selection.ids), encoding="utf-8")
    batch_count = (len(selection.ids) + INPUT_BATCH_SIZE - 1) // INPUT_BATCH_SIZE
    print(
        f"Rerun selection: not-found={selection.not_found_count} "
        f"error={selection.error_count} duplicates_removed={selection.duplicates_removed} "
        f"total_unique={len(selection.ids)}"
    )
    crawl_args = [
        "--start-batch", "1", "--end-batch", str(batch_count),
        "--selenium-call-size", str(args.selenium_call_size),
        "--concurrency-per-browser", str(args.concurrency_per_browser),
        "--run-dir", str(args.run_dir),
    ]
    with patch.object(orchestration, "DEFAULT_INPUT_FILE", input_path):
        run_crawl_command(crawl_args)
    print(json.dumps(write_summary(args.run_dir, args.source_run, selection), indent=2))


if __name__ == "__main__":
    main()
