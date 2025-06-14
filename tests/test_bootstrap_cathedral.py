from __future__ import annotations

import json
from pathlib import Path

import bootstrap_cathedral as bc


def test_creates_missing_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("VAR=1")
    bc.main()

    assert (tmp_path / "gui/cathedral_gui.py").exists()
    assert (tmp_path / "model_bridge.py").exists()
    assert (tmp_path / "tests/test_cathedral_boot.py").exists()
    assert (tmp_path / ".env").read_text() == "VAR=1"

    log = tmp_path / "logs/bootstrap_run.jsonl"
    assert log.exists()
    data = [json.loads(l) for l in log.read_text().splitlines()]
    assert any(e.get("action") == "complete" for e in data)
