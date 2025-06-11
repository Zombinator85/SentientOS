"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from pathlib import Path


def test_lock_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("requirements-lock.txt", "requirements-src-lock.txt"):
        path = root / name
        assert path.exists(), f"missing {name}"
        lines = path.read_text().splitlines()
        assert lines[0].startswith('#')
        assert any("--hash=" in l for l in lines)

