import importlib
import sys
from pathlib import Path
import pytest

import sentientos.admin_utils as admin_utils


def test_avatar_memory_linker(tmp_path, monkeypatch):
    log = tmp_path / "link.jsonl"
    monkeypatch.setenv("AVATAR_MEMORY_LINK_LOG", str(log))
    import sentientos.avatar_memory_linker as aml
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    importlib.reload(aml)
    aml.log_link("ava", "created", mood="joy", memory="m1")
    assert log.exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 1


def test_avatar_council_blessing(tmp_path, monkeypatch):
    log = tmp_path / "council.jsonl"
    monkeypatch.setenv("AVATAR_COUNCIL_LOG", str(log))
    import sentientos.avatar_council_blessing as acb
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    importlib.reload(acb)
    acb.log_vote("ava", "alice")
    assert acb.check_quorum("ava", quorum=1)
    lines = log.read_text().splitlines()
    assert len(lines) >= 2


def test_avatar_retirement(tmp_path, monkeypatch):
    log = tmp_path / "retire.jsonl"
    arch = tmp_path / "arch"
    src = tmp_path / "a.blend"
    src.write_text("data")
    monkeypatch.setenv("AVATAR_RETIRE_LOG", str(log))
    import sentientos.avatar_retirement as ar
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    importlib.reload(ar)
    ar.retire_avatar(src, arch, mood="peace", reason="end")
    assert (arch / "a.blend").exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 1
