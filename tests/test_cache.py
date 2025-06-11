"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os, sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from privilege_lint.cache import LintCache
from privilege_lint.config import LintConfig
import privilege_lint as pl


def test_cache_hit(tmp_path: Path) -> None:
    file = tmp_path / "a.py"
    file.write_text("\n".join(pl.BANNER_ASCII + [pl.FUTURE_IMPORT]), encoding="utf-8")
    cfg = LintConfig()
    cache = LintCache(tmp_path, cfg, enabled=True)
    linter = pl.PrivilegeLinter(cfg, project_root=tmp_path)
    linter.cache = cache
    assert not cache.is_valid(file)
    linter.validate(file)
    cache.update(file)
    cache.save()
    cache2 = LintCache(tmp_path, cfg, enabled=True)
    assert cache2.is_valid(file)
