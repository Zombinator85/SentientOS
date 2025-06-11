"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import importlib
import json

import workflow_controller as wc
import workflow_analytics as wa
import workflow_recommendation as rec
import workflow_library as wl


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_LIBRARY", str(tmp_path / "lib"))
    importlib.reload(wc)
    importlib.reload(wa)
    importlib.reload(rec)
    importlib.reload(wl)
    wl.LIB_DIR.mkdir(exist_ok=True)


def create_workflow(tmp_path, name="demo", fail=False):
    steps = [
        {"name": "s1", "action": (lambda: (_ for _ in ()).throw(RuntimeError("x"))) if fail else (lambda: None)},
    ]
    wc.register_workflow(name, steps)


def test_usage_and_recommend(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    create_workflow(tmp_path, "good")
    create_workflow(tmp_path, "bad", fail=True)
    assert wc.run_workflow("good")
    assert not wc.run_workflow("bad")
    data = wa.analytics()
    assert data["usage"]["good"]["runs"] == 1
    assert data["usage"]["bad"]["failures"] == 1
    recs = rec.recommend_workflows(data)
    assert any("bad" in r for r in recs)


def test_ai_edit(tmp_path, monkeypatch):
    path = tmp_path / "wf.json"
    path.write_text(json.dumps({"name": "demo", "steps": [{"name": "b"}, {"name": "a"}]}))
    import workflow_editor as we
    importlib.reload(we)
    data = we.load_file(path)
    new, expl = we.ai_suggest_edits(data)
    assert "Reordered" in expl
    assert new["steps"][0]["name"] == "a"
