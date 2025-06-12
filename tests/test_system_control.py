"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import input_controller as ic
import ui_controller as uc


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    reload(ic)
    reload(uc)


def test_input_logging(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    controller = ic.InputController()
    controller.type_text("hi", persona="Alice")
    log = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any("input.type_text" in l and "Alice" in l for l in log)


def test_ui_logging(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    uctrl = uc.UIController()
    uctrl.click_button("OK", persona="Bob")
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any("ui.click_button" in l and "Bob" in l for l in lines)


def test_panic(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    ic.trigger_panic()
    with pytest.raises(RuntimeError):
        controller = ic.InputController()
        controller.type_text("fail")
    ic.reset_panic()


def test_undo_last(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    controller = ic.InputController()
    controller.type_text("abc", persona="Alice")
    assert controller.undo_last(persona="Alice")
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any("input.undo" in l for l in lines)


def test_policy_denied(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    pol = tmp_path / "pol.yml"
    pol.write_text('{"policies":[{"conditions":{"event":"input.type_text"},"actions":[{"type":"deny"}]}]}')
    import importlib
    import policy_engine as pe
    importlib.reload(pe)
    engine = pe.PolicyEngine(str(pol))
    controller = ic.InputController(policy_engine=engine)
    with pytest.raises(PermissionError):
        controller.type_text("hi")
    log = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert any("policy_denied" in l for l in log)
