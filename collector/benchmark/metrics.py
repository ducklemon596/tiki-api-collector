"""Pure latency-statistic helpers used by benchmark summaries."""

import math
import statistics
from typing import Literal


def latency_metric(
    values: list[float], method: Literal["mean", "median", "p95"]
) -> float | None:
    """Return a rounded latency statistic, or ``None`` with no terminal samples."""
    if not values:
        return None
    if method == "mean":
        return round(statistics.mean(values), 4)
    if method == "median":
        return round(statistics.median(values), 4)
    return round(sorted(values)[math.ceil(len(values) * 0.95) - 1], 4)
