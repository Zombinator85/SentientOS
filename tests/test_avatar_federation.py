"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
from pathlib import Path

import avatar_federation as af


def test_export_and_import(tmp_path, monkeypatch):
    exp_log = tmp_path / "export.jsonl"
    imp_log = tmp_path / "import.jsonl"
    monkeypatch.setenv("AVATAR_EXPORT_LOG", str(exp_log))
    monkeypatch.setenv("AVATAR_IMPORT_LOG", str(imp_log))
    importlib.reload(af)

    avatar = tmp_path / "a.blend"
    avatar.write_text("data")
    tar = tmp_path / "a.tar.gz"
    af.export_avatar(avatar, tar, "share")
    dest = tmp_path / "recv"
    dest.mkdir()
    af.import_avatar(tar, dest, "recv")

    assert tar.exists()
    assert (dest / "a.blend").exists()
    assert len(exp_log.read_text().splitlines()) == 1
    assert len(imp_log.read_text().splitlines()) == 1

