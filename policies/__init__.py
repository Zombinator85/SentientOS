from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import List, Callable

from privilege_lint.config import LintConfig

Plugin = Callable[[Path, LintConfig], List[str]]


def load_policy(name: str, root: Path) -> List[Plugin]:
    if not name:
        return []
    try:
        spec = import_module(f"policies.{name}")
    except Exception:
        return []
    rules = []
    if hasattr(spec, "register"):
        try:
            rules.extend(spec.register())
        except Exception:
            pass
    else:
        for attr in dir(spec):
            obj = getattr(spec, attr)
            if callable(obj):
                rules.append(obj)
    return rules
