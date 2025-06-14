"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import os
import sys
import types
from importlib import reload
from pathlib import Path

import model_bridge as mb
import pytest


def setup_openai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("MODEL_BRIDGE_LOG", str(log))
    monkeypatch.setenv("MODEL_SLUG", "openai/gpt-4o")
    stub = types.SimpleNamespace(
        ChatCompletion=types.SimpleNamespace(
            create=lambda model, messages: types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))]
            )
        )
    )
    monkeypatch.setitem(sys.modules, "openai", stub)
    return log


def test_send_openai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = setup_openai(tmp_path, monkeypatch)
    reload(mb)
    res = mb.send_message("hi", system_prompt="test")
    assert res["response"] == "ok"
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert lines[-1]["prompt"] == "hi"
    assert lines[-1]["response"] == "ok"


def test_send_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local_path = tmp_path / "local_model.py"
    local_path.write_text("def generate(t):\n    return 'local:' + t\n")
    monkeypatch.setenv("MODEL_BRIDGE_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("MODEL_SLUG", "local/custom")
    monkeypatch.setenv("LOCAL_MODEL_PATH", str(local_path))
    reload(mb)
    res = mb.send_message("hello", system_prompt="sys", emotion="joy", emit=False)
    assert res["response"] == "local:hello"
    log_path = Path(os.environ["MODEL_BRIDGE_LOG"])
    data = json.loads(log_path.read_text().strip())
    assert data["emotion"] == "joy"
