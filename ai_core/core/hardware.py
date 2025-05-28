"""Hardware detection helpers for runtime routing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable


def parse_total_ram_gb(meminfo_text: str) -> float:
    """Parse total RAM in gigabytes from /proc/meminfo contents."""
    for line in meminfo_text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2:
                total_kb = int(parts[1])
                return total_kb / (1024 * 1024)
    raise RuntimeError("could not detect total system RAM")


def detect_hardware_info(
    meminfo_path: str | Path = "/proc/meminfo",
    cpu_count_provider: Callable[[], int | None] = os.cpu_count,
) -> dict[str, int | float]:
    """Return basic hardware information for model runtime selection."""
    try:
        meminfo_text = Path(meminfo_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"failed to read hardware information: {exc}") from exc

    cpu_cores = cpu_count_provider()
    if cpu_cores is None or cpu_cores < 1:
        cpu_cores = 1

    return {
        "ram_gb": parse_total_ram_gb(meminfo_text),
        "cpu_cores": int(cpu_cores),
    }
