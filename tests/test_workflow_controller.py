"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
import importlib
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

wc = None


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import memory_manager as mm
    importlib.reload(mm)
    global wc
    if wc is None:
        import workflow_controller as _wc
        wc = _wc
    importlib.reload(wc)


def test_workflow_success(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    steps = [
        {"name": "step1", "action": lambda: (tmp_path / "a.txt").write_text("x"), "undo": lambda: os.remove(tmp_path / "a.txt")},
        {"name": "step2", "action": lambda: None, "undo": lambda: None},
    ]
    wc.register_workflow("demo", steps)
    assert wc.run_workflow("demo")
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert any("workflow.end" in l and '"status": "ok"' in l for l in lines)
    assert any('"tag": "run:workflow"' in l for l in lines)


def test_workflow_failure_rollback(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    marker = {"undone": False}

    def fail():
        raise RuntimeError("oops")

    def undo():
        marker["undone"] = True

    steps = [
        {"name": "s1", "action": lambda: None, "undo": undo},
        {"name": "s2", "action": fail, "undo": lambda: None},
    ]
    wc.register_workflow("demo", steps)
    assert not wc.run_workflow("demo")
    assert marker["undone"]
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert any("workflow.undo" in l for l in lines)


def test_workflow_policy_denied(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    pol = tmp_path / "pol.yml"
    pol.write_text('{"policies":[{"conditions":{"event":"workflow.demo.step2"},"actions":[{"type":"deny"}]}]}')
    import policy_engine as pe
    importlib.reload(pe)
    engine = pe.PolicyEngine(str(pol))
    steps = [
        {"name": "step1", "action": lambda: None, "undo": lambda: None, "policy_event": "workflow.demo.step1"},
        {"name": "step2", "action": lambda: None, "undo": lambda: None, "policy_event": "workflow.demo.step2"},
    ]
    wc.register_workflow("demo", steps)
    assert not wc.run_workflow("demo", policy_engine=engine)
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert any('"status": "denied"' in l for l in lines)


def test_workflow_policy_logging(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    pol = tmp_path / "pol.yml"
    pol.write_text('{"policies":[{"conditions":{"event":"workflow.demo.step1"},"actions":[{"type":"deny"}]}]}')
    import policy_engine as pe
    importlib.reload(pe)
    engine = pe.PolicyEngine(str(pol))
    steps = [
        {"name": "step1", "action": lambda: None, "undo": lambda: None, "policy_event": "workflow.demo.step1"},
    ]
    wc.register_workflow("demo", steps)
    assert not wc.run_workflow("demo", policy_engine=engine, agent="agent1", persona="Lumos")
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    events = [json.loads(l) for l in lines]
    assert any(e["event"] == "workflow.policy" for e in events)
    assert any(e["payload"].get("persona") == "Lumos" for e in events)


def test_review_logs_creates_reflection(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    steps = [
        {"name": "s1", "action": lambda: (_ for _ in ()).throw(RuntimeError("x")), "undo": lambda: None},
    ]
    wc.register_workflow("demo", steps)
    wc.run_workflow("demo")
    wc.review_workflow_logs(threshold=1)
    raw = tmp_path / "raw"
    files = list(raw.glob("*.json"))
    assert files, "reflection saved"


def test_load_workflow_file(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    actions = tmp_path / "actions.py"
    actions.write_text(
        """
def act(path):
    with open(path, 'w') as f:
        f.write('hi')

def undo(path):
    pass
""",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    wf = tmp_path / "wf.json"
    wf.write_text(
        (
            '{"name":"demo_file","steps":[{"name":"s1","action":"actions.act","params":{"path":"'
            + str(tmp_path / "out.txt")
            + '"},"undo":"actions.undo"}]}'
        ),
        encoding="utf-8",
    )
    wc.load_workflow_file(str(wf))
    assert "demo_file" in wc.WORKFLOWS
    assert wc.run_workflow("demo_file")
    assert (tmp_path / "out.txt").exists()


def test_on_fail_hook(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    flag = {"called": False}

    def fail():
        raise RuntimeError("boom")

    def handle():
        flag["called"] = True

    steps = [
        {"name": "s1", "action": fail, "undo": lambda: None, "on_fail": [handle]},
    ]
    wc.register_workflow("demo_fail", steps)
    assert not wc.run_workflow("demo_fail")
    assert flag["called"]

