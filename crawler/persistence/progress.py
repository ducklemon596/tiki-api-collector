"""Durable active-time and terminal-latency journal persistence."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import ujson as json

from persistence.checkpoint import write_json_atomically

if TYPE_CHECKING:
    from browser.classification import ClassifiedResults


def append_terminal_metrics(path: Path, results: ClassifiedResults) -> None:
    """Append and fsync latency rows for newly terminal results before checkpointing."""
    if not results:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as destination:
        for result in results:
            json.dump(
                {
                    "id": result.response.product_id,
                    "classification": result.classification,
                    "elapsed_seconds": result.response.elapsed_seconds,
                },
                destination,
            )
            destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())


def append_error_journal(path: Path, results: ClassifiedResults) -> None:
    """Append resumable browser-error IDs without treating them as terminal."""
    errors = [result for result in results if result.classification == "error"]
    if not errors:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as destination:
        for result in errors:
            response = result.response
            json.dump(
                {
                    "id": response.product_id,
                    "classification": "error",
                    "error": response.error,
                    "timestamp": response.ended_at,
                },
                destination,
            )
            destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())


def load_terminal_metrics(path: Path, completed_ids: set[int]) -> list[float]:
    """Read the latest durable latency for each checkpointed terminal ID."""
    if not path.exists():
        return []
    latest: dict[int, float] = {}
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            try:
                record: object = json.loads(line)
                if not isinstance(record, dict):
                    continue
                product_id = int(record["id"])
                latest[product_id] = float(record["elapsed_seconds"])
            except (KeyError, TypeError, ValueError):
                continue
    return [latency for product_id, latency in latest.items() if product_id in completed_ids]


def load_active_elapsed(path: Path) -> float:
    """Load cumulative active worker seconds, treating a missing file as a new run."""
    if not path.exists():
        return 0.0
    with path.open("r", encoding="utf-8") as source:
        record: object = json.load(source)
    if not isinstance(record, dict):
        raise ValueError(f"Invalid active elapsed state in {path}")
    elapsed = float(record.get("active_elapsed_seconds", 0))
    if elapsed < 0:
        raise ValueError(f"Negative active elapsed time in {path}")
    return elapsed


def save_active_elapsed(path: Path, seconds: float) -> float:
    """Atomically persist cumulative active worker seconds and return the stored value."""
    persisted = round(seconds, 3)
    write_json_atomically(path, {"active_elapsed_seconds": persisted})
    return persisted
