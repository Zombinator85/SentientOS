from __future__ import annotations

from pathlib import Path
from typing import List

from privilege_lint.config import LintConfig


def doctrinal_banner(path: Path, cfg: LintConfig) -> List[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# DOCTRINAL BANNER"):
        return [f"{path}:1 missing doctrinal banner"]
    return []


def register() -> List[callable]:
    return [doctrinal_banner]
