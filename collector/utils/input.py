"""Product-ID input loading and deterministic logical batching."""

from pathlib import Path


def load_and_batch_ids(
    file_path: Path, batch_size: int = 1_000
) -> tuple[list[list[int]], int]:
    """Read valid IDs, preserve first-seen order, and split them into logical batches."""
    if not file_path.exists():
        return [], 0
    with file_path.open("r", encoding="utf-8") as source:
        unique_ids = list(
            dict.fromkeys(
                int(line.strip()) for line in source if line.strip().isdigit()
            )
        )
    return (
        [
            unique_ids[index : index + batch_size]
            for index in range(0, len(unique_ids), batch_size)
        ],
        len(unique_ids),
    )
