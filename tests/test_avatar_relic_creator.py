import importlib
import json
import os
import sys
from pathlib import Path
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
    monkeypatch.setattr(arc, "LOG_PATH", relic_log, raising=False)
    monkeypatch.setitem(aag.LOG_PATHS, "relic", relic_log)
    arc.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    mm.append_memory("hello from ava", tags=["ava"])
    mm.append_memory("other", tags=["bob"])

    asset_dir = tmp_path / "avatars" / "ava"
    asset_dir.mkdir(parents=True)
    meta = asset_dir / "meta.txt"
    meta.write_text("data")
    monkeypatch.setenv("AVATAR_DIR", str(tmp_path / "avatars"))
    monkeypatch.setenv("ARCHIVE_DIR", str(tmp_path / "arch"))

    entry = arc.extract("ava", "token")
    assert relic_log.exists()
    data = json.loads(relic_log.read_text().splitlines()[0])
    assert data["avatar"] == "ava"
    assert entry["info"]["fragments"] == ["hello from ava"]

    relic_path = Path(os.environ["ARCHIVE_DIR"]) / "relics" / "ava" / "token"
    assert (relic_path / "meta.txt").exists()
    assert (relic_path / "manifest.json").exists()

