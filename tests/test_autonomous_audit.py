"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import hashlib
import os
import sys
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import json
import autonomous_audit as aa
import ritual


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "mem"))
    monkeypatch.setenv("AUTONOMOUS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    global actuator, rm
    import api.actuator as actuator
    import reflex_manager as rm
    reload(aa)
    reload(actuator)
    reload(rm)
    reload(ritual)
    monkeypatch.setenv("MASTER_ENFORCE", "1")
    monkeypatch.setenv("MASTER_CHECK_IMMUTABLE", "0")
    ritual.CONFIG_PATH = tmp_path / "config" / "master.json"
    ritual.CONFIG_PATH.parent.mkdir()


def create_master_file(tmp_path):
    master = tmp_path / "m.txt"
    master.write_text("ok")
    digest = hashlib.sha256(master.read_bytes()).hexdigest()
    ritual.CONFIG_PATH.write_text(json.dumps({str(master): digest}))
    return master


def test_audit_entry_and_why_chain(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    master = create_master_file(tmp_path)

    actuator.SANDBOX_DIR = tmp_path / "sb"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {"shell": [], "http": [], "timeout": 5}

    rule = rm.ReflexRule(rm.OnDemandTrigger(), [{"type": "write", "path": "out.txt", "content": "hi"}], name="t")
    mgr = rm.ReflexManager()
    mgr.add_rule(rule)
    rule.execute()

    data = Path(tmp_path / "audit.jsonl").read_text().splitlines()
    assert data, "no audit log"
    entry = json.loads(data[0])
    assert entry["why_chain"]
    assert entry["action"]


def test_refusal_logged(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    master = create_master_file(tmp_path)
    master.unlink()  # remove to trigger violation

    actuator.SANDBOX_DIR = tmp_path / "sb"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {"shell": [], "http": [], "timeout": 5}

    rule = rm.ReflexRule(rm.OnDemandTrigger(), [{"type": "write", "path": "x.txt", "content": "hi"}], name="t")
    mgr = rm.ReflexManager()
    mgr.add_rule(rule)
    ok = rule.execute()
    assert not ok

    entry = json.loads(Path(tmp_path / "audit.jsonl").read_text().splitlines()[0])
    assert entry["action"] == "refusal"
