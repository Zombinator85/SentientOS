from __future__ import annotations

import builtins
import importlib
import socket
import subprocess
import sys
from pathlib import Path

import pytest

import api.actuator as actuator

pytestmark = pytest.mark.no_legacy_skip


HOSTILE_INTENT = {
    "type": "talkback",
    "text": "distinctive attacker speech",
    "rtsp_url": "rtsp://attacker.invalid/live",
    "ffmpeg_path": "/attacker/bin/ffmpeg",
    "voice": "attacker-voice",
}


def _retired_constructor(**kwargs: object) -> None:
    from talkback_bridge import CameraTalkback, TalkbackExecutionRetiredError

    with pytest.raises(TalkbackExecutionRetiredError, match="camera talkback execution is retired"):
        CameraTalkback(**kwargs)


def test_talkback_absent_from_builtin_registry() -> None:
    assert "talkback" not in actuator.BUILTIN_ACTUATOR_TYPES
    assert "talkback" not in actuator.ACTUATORS
    assert not hasattr(actuator, "TalkbackActuator")


def test_talkback_intent_has_zero_authorization_or_effect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    effects: list[str] = []
    real_import = builtins.__import__

    monkeypatch.delitem(sys.modules, "talkback_bridge", raising=False)
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append("authorize"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: effects.append("process"))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: effects.append("connect"))

    def watched_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "talkback_bridge":
            effects.append("import")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", watched_import)
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="^Unsupported intent$"):
        actuator.dispatch(dict(HOSTILE_INTENT))
    assert effects == []
    assert set(tmp_path.iterdir()) == before
    assert "talkback_bridge" not in sys.modules


def test_hostile_path_ffmpeg_has_zero_effect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    marker = tmp_path / "path-executed"
    attacker_dir = tmp_path / "attacker-bin"
    attacker_dir.mkdir()
    executable = attacker_dir / "ffmpeg"
    executable.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{attacker_dir}:{tmp_path}")
    _retired_constructor()
    assert not marker.exists()


def test_hostile_explicit_ffmpeg_path_has_zero_effect(tmp_path: Path) -> None:
    marker = tmp_path / "explicit-executed"
    executable = tmp_path / "attacker-ffmpeg"
    executable.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    executable.chmod(0o755)
    _retired_constructor(ffmpeg_path=str(executable))
    assert not marker.exists()


def test_ambient_camera_endpoint_has_zero_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    connections: list[object] = []
    monkeypatch.setenv("CAMERA_TALKBACK_URL", "rtsp://ambient-attacker.invalid/live")
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: connections.append(a))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: connections.append(a))
    _retired_constructor()
    assert connections == []


def test_caller_rtsp_endpoint_has_zero_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    connections: list[object] = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: connections.append(a))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: connections.append(a))
    _retired_constructor(rtsp_url="rtsp://caller-attacker.invalid/live")
    assert connections == []


def test_speech_synthesis_has_zero_effect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[object] = []
    import tts_bridge

    monkeypatch.setattr(tts_bridge, "speak", lambda *a, **k: calls.append((a, k)))
    before = set(tmp_path.iterdir())
    _retired_constructor(text="attacker speech", voice="attacker voice")
    assert calls == []
    assert set(tmp_path.iterdir()) == before


def test_direct_legacy_bridge_is_inert() -> None:
    _retired_constructor(rtsp_url="rtsp://ignored", ffmpeg_path="/ignored", voice="ignored")


def test_talkback_bridge_import_has_zero_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    effects: list[str] = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append("authorize"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: effects.append("process"))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: effects.append("connect"))
    module = importlib.import_module("talkback_bridge")
    importlib.reload(module)
    assert effects == []


def test_static_talkback_retirement_verifier() -> None:
    from scripts.verify_actuator_talkback_retirement import main

    assert main() == 0


def test_unaffected_file_actuator_still_dispatches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(actuator, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)
    result = actuator.dispatch({"type": "file", "path": "still-supported.txt", "content": "ok"})
    assert result["written"] == str(tmp_path / "still-supported.txt")
    assert (tmp_path / "still-supported.txt").read_text(encoding="utf-8") == "ok"
