"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import json
from pathlib import Path
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import avatar_relic_creator as arc


def test_extract_records_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "mem"))
    import memory_manager as mm
    importlib.reload(mm)
    importlib.reload(arc)
    import avatar_artifact_gallery as aag
    importlib.reload(aag)

    relic_log = tmp_path / "relics.jsonl"
    monkeypatch.setenv("AVATAR_RELIC_LOG", str(relic_log))
    monkeypatch.setitem(aag.LOG_PATHS, "relic", relic_log)
    importlib.reload(arc)

    mm.append_memory("hello from ava", tags=["ava"])
    mm.append_memory("other", tags=["bob"])

    entry = arc.extract("ava", "token")
    assert relic_log.exists()
    data = json.loads(relic_log.read_text().splitlines()[0])
    assert data["avatar"] == "ava"
    assert entry["info"]["fragments"] == ["hello from ava"]


def test_log_path_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AVATAR_RELIC_LOG", str(tmp_path / "custom.jsonl"))
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    import importlib
    import avatar_relic_creator as arc
    importlib.reload(arc)

    arc.log_relic("ava", "token", {"fragments": []})
    assert Path(arc.LOG_PATH).resolve() == (tmp_path / "custom.jsonl").resolve()
    assert arc.LOG_PATH.exists()

