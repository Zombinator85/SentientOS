"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import ast
from pathlib import Path
from typing import Iterable

SANCTUARY_LINE = "Sanctuary Privilege Ritual: Do not remove. See doctrine for details."


def iter_script_files() -> Iterable[Path]:
    for folder in ("scripts", "sentientos"):
        for path in Path(folder).rglob("*.py"):
            yield path


def test_sanctuary_docstring_present() -> None:
    missing: list[Path] = []
    for path in iter_script_files():
        module = ast.parse(path.read_text(encoding="utf-8"))
        body = module.body
        idx = 0
        while idx < len(body) and isinstance(body[idx], ast.ImportFrom) and body[idx].module == "__future__":
            idx += 1
        if idx >= len(body):
            missing.append(path)
            continue
        node = body[idx]
        if not (
            isinstance(node, ast.Expr)
            and isinstance(getattr(node, "value", None), (ast.Str, ast.Constant))
            and (
                node.value.s if hasattr(node.value, "s") else node.value.value
            )
            == SANCTUARY_LINE
        ):
            missing.append(path)
    assert not missing, f"Missing ritual docstring in: {', '.join(str(p) for p in missing)}"
