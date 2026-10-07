from __future__ import annotations

import json
import importlib
import sys
import types
from importlib import reload
from pathlib import Path

import emotion_pump as ep
import pytest


def test_emotion_pump_import_is_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    import sentientos.privilege as privilege
    import emotion_udp_bridge

    monkeypatch.setattr(privilege, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: events.append("lumos"))
    monkeypatch.setattr(
        emotion_udp_bridge,
        "EmotionUDPBridge",
        lambda *_args, **_kwargs: events.append("bridge"),
    )
    sys.modules.pop("emotion_pump", None)

    imported = importlib.import_module("emotion_pump")

    assert imported is not None
    assert events == []


def test_emotion_pump_run_authorizes_before_runtime_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class StopRun(Exception):
        pass

    class LogProbe:
        def exists(self) -> bool:
            events.append("log")
            raise StopRun

    monkeypatch.setattr(ep, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(ep, "require_lumos_approval", lambda: events.append("lumos"))
    monkeypatch.setattr(
        ep,
        "EmotionUDPBridge",
        lambda *_args, **_kwargs: events.append("bridge"),
    )
    monkeypatch.setattr(ep, "LOG_FILE", LogProbe())
    monkeypatch.setattr(ep.time, "sleep", lambda *_args: events.append("sleep"))

    with pytest.raises(StopRun):
        ep.run()

    assert events == ["admin", "lumos", "bridge", "log"]


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


def test_emotion_pump_model_bridge_log_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("MODEL_BRIDGE_LOG", str(log))
    monkeypatch.setenv("MODEL_PROVIDER", "llama_cpp")
    import model_bridge as mb
    reload(mb)
    local = types.SimpleNamespace(
        create_chat_completion=lambda *, messages: {
            "choices": [{"message": {"content": "ok"}}]
        }
    )
    monkeypatch.setattr(mb, "_initialise_llama", lambda: local)
    mb.send_message("hi", system_prompt="sys", emotion="Joy", emit=False)
    data = json.loads(log.read_text().splitlines()[-1])
    assert data["model"] == "Mistral-7B Instruct v0.2 (GGUF)"
    assert "emotion" in data and "latency_ms" in data
