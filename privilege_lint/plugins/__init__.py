from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Callable, List

from privilege_lint.config import LintConfig

Plugin = Callable[[Path, LintConfig], List[str]]


def load_plugins() -> List[Plugin]:
    eps: list[Any] = entry_points().get("privilege_lint.plugins", [])
    plugins: List[Plugin] = []
    for ep in eps:
        try:
            obj = ep.load()
            if callable(obj):
                plugins.append(obj)
        except Exception:
            continue
    return plugins
