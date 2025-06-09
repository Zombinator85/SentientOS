from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
from pathlib import Path
from typing import Sequence, Iterable
import os


DEFAULT_WORKERS = max(cpu_count() - 1, 1)


def parallel_validate(linter: "PrivilegeLinter", files: Sequence[Path], max_workers: int | None = None) -> list[str]:
    """Validate files in parallel using threads."""
    workers = max_workers if max_workers is not None else DEFAULT_WORKERS
    issues: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as exe:
        futures = {exe.submit(linter.validate, f): f for f in files}
        for fut in as_completed(futures):
            issues.extend(fut.result())
    return issues


def iter_data_files(paths: Iterable[str]) -> list[Path]:
    result: list[Path] = []
    for base in paths:
        root = Path(base)
        if not root.exists():
            continue
        for ext in ("*.json", "*.csv"):
            for p in root.rglob(ext):
                result.append(p)
    return sorted(set(result))
