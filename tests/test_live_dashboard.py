"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import storymaker
import replay
import tts_bridge


def test_live_capture(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "memory.jsonl").write_text(json.dumps({"timestamp":"2024-01-01T10:00:00","text":"start"})+"\n")
    monkeypatch.setattr(tts_bridge, "speak", lambda *a, **k: str(tmp_path/"a.mp3"))
    monkeypatch.setattr(time, "sleep", lambda x: None)
    out = tmp_path / "live.json"
    storymaker.run_live(str(out), log_dir, dry_run=True, limit=1, poll=0)
    data = json.loads(out.read_text())
    assert data["chapters"]


def test_dashboard_display(tmp_path):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({"chapters":[{"chapter":1,"title":"A"}]}))
    app = replay.run_dashboard(str(sb))
    client = app.test_client()
    res = client.post("/chapters")
    data = res.data if isinstance(res.data, str) else res.data.decode()
    assert "A" in data


def test_feedback_workflow(tmp_path, monkeypatch):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({"chapters":[{"chapter":1,"title":"A","t_start":0,"t_end":0.1}]}))
    monkeypatch.setattr(time, "sleep", lambda x: None)
    monkeypatch.setattr("builtins.input", lambda prompt='': "ok")
    replay.playback(str(sb), headless=True, feedback_enabled=True)
    fb = sb.with_suffix(".feedback.jsonl")
    assert fb.exists() and "ok" in fb.read_text()


def test_analytics_export(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "memory.jsonl").write_text(json.dumps({"timestamp":"2024-01-01T09:00:00","text":"a"})+"\n")
    (log_dir / "emotions.jsonl").write_text(json.dumps({"timestamp":"2024-01-01T09:10:00","emotions":{"Joy":1.0}})+"\n")
    csv_path = tmp_path / "out.csv"
    storymaker.export_analytics("2024-01-01 00:00","2024-01-01 23:59", log_dir, str(csv_path))
    data = csv_path.read_text()
    assert "chapter" in data and "joy" in data
