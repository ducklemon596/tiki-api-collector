"""Append-only terminal checkpoints and atomic benchmark metadata persistence."""

import os
from datetime import UTC, datetime
from pathlib import Path
import time
from typing import TextIO, TypeAlias, TypeGuard

import ujson as json

from persistence.paths import STATE_FILE_NAME, RunPaths, batch_checkpoint_paths
from utils.product import ProductRecord

JsonLineRecord: TypeAlias = dict[str, object]


def _is_json_record(value: object) -> TypeGuard[JsonLineRecord]:
    """Return whether decoded JSON is a string-keyed record."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def write_json_atomically(path: Path, data: object) -> None:
    """Flush a temporary JSON file, then atomically replace its destination.

    Windows observers can briefly lock a metadata file, so replacement keeps the
    existing short retry behavior used by worker progress and benchmark summaries.
    """
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as destination:
        json.dump(data, destination, ensure_ascii=False, indent=2)
        destination.flush()
        os.fsync(destination.fileno())
    for attempt in range(6):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def prepare_manifest(paths: RunPaths, configuration: dict[str, object]) -> None:
    """Create or validate the immutable configuration for a resumable run."""
    if paths.manifest.exists():
        with paths.manifest.open("r", encoding="utf-8") as source:
            existing = json.load(source)
        if existing != configuration:
            raise ValueError(
                f"Run directory has a different benchmark manifest: {paths.manifest}"
            )
        return
    write_json_atomically(paths.manifest, configuration)


def _read_jsonl(path: Path) -> list[JsonLineRecord]:
    """Read a checkpoint journal and truncate only an incomplete final record."""
    if not path.exists():
        return []
    with path.open("rb") as source:
        lines: list[tuple[int, bytes]] = []
        while raw_line := source.readline():
            lines.append((source.tell() - len(raw_line), raw_line))

    records: list[JsonLineRecord] = []
    non_empty_indexes = [index for index, (_, line) in enumerate(lines) if line.strip()]
    last_non_empty_index = non_empty_indexes[-1] if non_empty_indexes else -1
    for index, (offset, raw_line) in enumerate(lines):
        if not raw_line.strip():
            continue
        try:
            record: object = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            if index == last_non_empty_index:
                with path.open("r+b") as checkpoint:
                    checkpoint.truncate(offset)
            continue
        if _is_json_record(record):
            records.append(record)
    return records


class BatchCheckpoint:
    """Append-only terminal journals and immutable final output for one batch."""

    def __init__(self, run_dir: Path, batch_num: int, sync_interval: int = 50):
        self.run_dir = run_dir
        self.batch_num = batch_num
        self.sync_interval = sync_interval
        paths = batch_checkpoint_paths(run_dir, batch_num)
        self.success_dir = paths.success_dir
        self.not_found_dir = paths.not_found_dir
        self.final_dir = paths.final_dir
        for directory in (self.success_dir, self.not_found_dir, self.final_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.success_path = paths.success_file
        self.not_found_path = paths.not_found_file
        self.final_path = paths.final_file
        self._success_file: TextIO | None = None
        self._not_found_file: TextIO | None = None
        self._records_since_sync = 0

    @property
    def finalized(self) -> bool:
        """Return whether immutable final output already exists for this batch."""
        return self.final_path.exists()

    def load_completed(self) -> tuple[list[ProductRecord], set[int]]:
        """Return successful products and every durable terminal product ID."""
        success_records = _read_jsonl(self.success_path)
        terminal_records = [*success_records, *_read_jsonl(self.not_found_path)]
        completed_ids: set[int] = set()
        for record in terminal_records:
            record_id = record.get("id")
            if isinstance(record_id, int) and not isinstance(record_id, bool):
                completed_ids.add(record_id)
            elif isinstance(record_id, str) and record_id.isdigit():
                completed_ids.add(int(record_id))
        return success_records, completed_ids

    def open(self) -> None:
        """Open the append-only journals owned exclusively by this worker."""
        self._success_file = self.success_path.open("a", encoding="utf-8")
        self._not_found_file = self.not_found_path.open("a", encoding="utf-8")

    def _append(self, handle: TextIO, record: JsonLineRecord) -> bool:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._records_since_sync += 1
        if self._records_since_sync >= self.sync_interval:
            self.flush()
            return True
        return False

    def record_success(self, product: ProductRecord) -> bool:
        """Append one terminal successful product."""
        if self._success_file is None:
            raise RuntimeError("Checkpoint is not open")
        return self._append(self._success_file, product)

    def record_not_found(self, product_id: int, status: int) -> bool:
        """Append one terminal 404/410 product."""
        if self._not_found_file is None:
            raise RuntimeError("Checkpoint is not open")
        return self._append(
            self._not_found_file,
            {"id": product_id, "status": status, "timestamp": datetime.now(UTC).isoformat()},
        )

    def flush(self) -> None:
        """Flush both journals and reset the configured sync counter."""
        for handle in (self._success_file, self._not_found_file):
            if handle is not None:
                handle.flush()
                os.fsync(handle.fileno())
        self._records_since_sync = 0

    def write_state(self, worker_id: str, success_count: int, not_found_count: int) -> None:
        """Write informational state; append-only journals remain authoritative."""
        write_json_atomically(
            self.run_dir / STATE_FILE_NAME,
            {
                "worker_id": worker_id,
                "current_batch": self.batch_num,
                "success_count": success_count,
                "not_found_count": not_found_count,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    def finalize(self) -> Path:
        """Create immutable final JSON only after its caller confirms completion."""
        self.flush()
        records, _ = self.load_completed()
        unique_records = {record.get("id"): record for record in records}
        write_json_atomically(self.final_path, list(unique_records.values()))
        return self.final_path

    def close(self) -> None:
        """Flush and close journal handles safely at a worker boundary."""
        self.flush()
        for handle in (self._success_file, self._not_found_file):
            if handle is not None:
                handle.close()
        self._success_file = None
        self._not_found_file = None
