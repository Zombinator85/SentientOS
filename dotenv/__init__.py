"""Lightweight fallback implementation of python-dotenv."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def load_dotenv(path: str | None = None, *, override: bool = False) -> bool:
    """Load environment variables from a `.env` file.

    This implementation only supports simple ``KEY=VALUE`` lines and ignores
    comments or shell expansions. It is sufficient for test environments where
    the full :mod:`python-dotenv` package is unavailable.
    """

    candidates: Iterable[Path]
    if path:
        candidates = [Path(path)]
    else:
        candidates = [Path.cwd() / ".env"]
    loaded = False
    for candidate in candidates:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = value
        loaded = True
        break
    return loaded


__all__ = ["load_dotenv"]
