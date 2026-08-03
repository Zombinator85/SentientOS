"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_lock_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("requirements-lock.txt", "requirements-src-lock.txt"):
        path = root / name
        assert path.exists(), f"missing {name}"
        lines = path.read_text().splitlines()
        assert lines[0].startswith('#')
        assert any("--hash=" in l for l in lines)


def test_default_lock_install_uses_one_lock_and_no_deps_project_install() -> None:
    source = (Path(__file__).resolve().parents[1] / "scripts/lock.py").read_text()
    install_body = source.split("def install()", 1)[1].split("def check()", 1)[0]
    assert '"-r", LOCKS[0]' in install_body
    assert '"--no-deps", "."' in install_body
    assert "for lock in LOCKS" not in install_body
