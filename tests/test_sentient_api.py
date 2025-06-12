from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from importlib import reload
from pathlib import Path

import sentient_api


def setup_app(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("EPU_STATE_CACHE", str(tmp_path / "state.json"))
    reload(sentient_api)
    return sentient_api.app.test_client()


def test_epu_state_updates(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.get("/epu/state")
    initial = resp.get_json()
    client.post("/memory", json={"text": "sample", "emotion": "reverent_hunger"})
    resp2 = client.get("/epu/state")
    after = resp2.get_json()
    assert any(after[e] != initial[e] for e in after)
