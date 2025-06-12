"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import importlib
import json

import workflow_controller as wc
import workflow_analytics as wa
import workflow_recommendation as rec
import workflow_library as wl
import review_requests as rr


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_LIBRARY", str(tmp_path / "lib"))
    monkeypatch.setenv("REVIEW_REQUESTS_FILE", str(tmp_path / "req.jsonl"))
    importlib.reload(wc)
    importlib.reload(wa)
    importlib.reload(rec)
    importlib.reload(wl)
    importlib.reload(rr)
    wl.LIB_DIR.mkdir(exist_ok=True)


def create_workflow(name="demo", fail=False):
    steps = [
        {"name": "s1", "action": (lambda: (_ for _ in ()).throw(RuntimeError("x"))) if fail else (lambda: None)},
    ]
    wc.register_workflow(name, steps)


def test_request_generation(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    create_workflow("bad", fail=True)
    for _ in range(3):
        try:
            wc.run_workflow("bad")
        except Exception:
            pass
    data = wa.analytics()
    rec.generate_review_requests(data)
    reqs = rr.list_requests()
    assert any(r.get("target") == "bad" for r in reqs)
