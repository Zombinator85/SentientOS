"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os, sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from privilege_lint.typing_rules import run_incremental
from privilege_lint.cache import LintCache
from privilege_lint.config import LintConfig


def test_incremental(tmp_path: Path) -> None:
    src = tmp_path / "a.py"
    src.write_text("def foo(x: int) -> int:\n    return x\n", encoding="utf-8")
    cfg = LintConfig(mypy_enabled=True)
    cache = LintCache(tmp_path, cfg, enabled=True)
    issues, checked = run_incremental([src], cache, strict=True)
    assert not issues
    assert checked == {src}
    cache.save()
    issues, _ = run_incremental([src], cache, strict=True)
    assert issues == []
    src.write_text("def foo(x: int):\n    return x\n", encoding="utf-8")
    issues, _ = run_incremental([src], cache, strict=True)
    assert any("error" in m for m in issues)
