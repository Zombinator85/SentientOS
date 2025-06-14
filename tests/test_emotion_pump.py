"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import sys
import types
from importlib import reload
from pathlib import Path

import emotion_pump as ep


def _write_log(path: Path, model: str, emotion: str) -> None:
    entry = {"prompt": "t", "response": "r", "model": model, "latency_ms": 1, "emotion": emotion}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def test_emotion_pump_latest_vector(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    _write_log(log, "openai/gpt-4o", "Anger")
    vec = ep.latest_vector(log)
    assert vec is not None
    anger_index = ep.EMOTIONS.index("Anger")
    assert vec[anger_index] == 1.0
    assert len(vec) == len(ep.EMOTIONS)


def test_emotion_pump_model_bridge_log_fields(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("MODEL_BRIDGE_LOG", str(log))
    monkeypatch.setenv("MODEL_SLUG", "openai/gpt-4o")
    sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
    stub = types.SimpleNamespace(
        ChatCompletion=types.SimpleNamespace(
            create=lambda model, messages: types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))]
            )
        )
    )
    monkeypatch.setitem(sys.modules, "openai", stub)
    import model_bridge as mb
    reload(mb)
    mb.send_message("hi", system_prompt="sys", emotion="Joy", emit=False)
    data = json.loads(log.read_text().splitlines()[-1])
    assert data["model"] == "openai/gpt-4o"
    assert "emotion" in data and "latency_ms" in data
