"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os, sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl
from privilege_lint.runner import parallel_validate


def test_parallel_matches_serial(tmp_path: Path) -> None:
    paths = []
    for i in range(20):
        p = tmp_path / f"f{i}.py"
        p.write_text("\n".join(pl.BANNER_ASCII + [pl.FUTURE_IMPORT, 'import os']), encoding="utf-8")
        paths.append(p)
    linter = pl.PrivilegeLinter()
    serial: list[str] = []
    for f in paths:
        serial.extend(linter.validate(f))
    parallel = parallel_validate(linter, paths, max_workers=4)
    assert sorted(serial) == sorted(parallel)
