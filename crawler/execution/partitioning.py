"""Deterministic input chunking and contiguous two-browser assignments."""

from collections.abc import Iterator
from typing import TypeAlias

ProductId: TypeAlias = int
BatchNumber: TypeAlias = int
BatchAssignment: TypeAlias = tuple[BatchNumber, list[ProductId]]
BrowserAssignment: TypeAlias = list[BatchAssignment]
BrowserAssignments: TypeAlias = list[BrowserAssignment]


def chunks(ids: list[ProductId], size: int) -> Iterator[list[ProductId]]:
    """Yield ordered Selenium-call-sized chunks from one pending-ID sequence."""
    for index in range(0, len(ids), size):
        yield ids[index : index + size]


def contiguous_assignments(
    selected: list[BatchAssignment], browser_count: int
) -> BrowserAssignments:
    """Split selected IDs into contiguous, deterministic browser partitions."""
    numbered_ids = [
        (batch_number, product_id)
        for batch_number, ids in selected
        for product_id in ids
    ]
    base_size, remainder = divmod(len(numbered_ids), browser_count)
    assignments: BrowserAssignments = []
    offset = 0
    for browser_index in range(browser_count):
        size = base_size + (1 if browser_index < remainder else 0)
        partition = numbered_ids[offset : offset + size]
        offset += size
        grouped: dict[BatchNumber, list[ProductId]] = {}
        for batch_number, product_id in partition:
            grouped.setdefault(batch_number, []).append(product_id)
        assignments.append(list(grouped.items()))
    return assignments
