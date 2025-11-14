from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Type

import pytest

from sentientos.runtime.shell import (
    DEFAULT_RUNTIME_CONFIG,
    RuntimeShell,
    ensure_runtime_dirs,
    load_or_init_config,
)


class DummyProcess:
    def __init__(self, name: str) -> None:
        self.name = name
        self._poll: int | None = None
        self.returncode: int | None = None
        self.terminate_called = False
        self.kill_called = False

    def poll(self) -> int | None:  # pragma: no cover - simple accessor
        return self._poll

    def wait(self, timeout: float | None = None) -> int:  # pragma: no cover - trivial
        return self.returncode or 0

    def terminate(self) -> None:  # pragma: no cover - trivial
        self.terminate_called = True

    def kill(self) -> None:  # pragma: no cover - fallback
        self.kill_called = True

    def exit(self, code: int) -> None:
        self._poll = code
        self.returncode = code


@pytest.fixture
def runtime_config(tmp_path: Path) -> Dict[str, object]:
    runtime_root = tmp_path
    data_dir = runtime_root / "sentientos_data"
    models_dir = data_dir / "models"
    config_dir = data_dir / "config"
    logs_dir = runtime_root / "logs"
    config = {
        "runtime": {
            **DEFAULT_RUNTIME_CONFIG,
            "llama_server_path": "C:/SentientOS/bin/llama-server.exe",
            "model_path": "C:/SentientOS/sentientos_data/models/demo.gguf",
            "relay_host": "127.0.0.1",
            "relay_port": 7000,
            "watchdog_interval": 0.01,
            "windows_mode": True,
            "root": str(runtime_root),
            "logs_dir": str(logs_dir),
            "data_dir": str(data_dir),
            "models_dir": str(models_dir),
            "config_dir": str(config_dir),
        }
    }
    config["persona"] = {
        "enabled": True,
        "tick_interval_seconds": 15.0,
        "max_message_length": 180,
    }
    return config


def _patch_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubThread:
        def __init__(self, target, daemon: bool | None = None) -> None:
            self._target = target
            self.daemon = daemon
            self.started = False

        def start(self) -> None:
            self.started = True

        def join(self, timeout: float | None = None) -> None:
            pass

    monkeypatch.setattr("sentientos.runtime.shell.threading.Thread", _StubThread)


def _patch_persona_loop(monkeypatch: pytest.MonkeyPatch) -> Type[object]:
    class _StubPersonaLoop:
        def __init__(self, *args, **kwargs) -> None:
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("sentientos.runtime.shell.PersonaLoop", _StubPersonaLoop)
    return _StubPersonaLoop


def _install_popen_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[List[tuple[str, List[str], Dict[str, object]]], Dict[str, DummyProcess]]:
    calls: List[tuple[str, List[str], Dict[str, object]]] = []
    processes: Dict[str, DummyProcess] = {}

    def identify(name_args: List[str]) -> str:
        joined = " ".join(name_args)
        if "--model" in name_args:
            return "llama"
        if "oracle_relay" in joined:
            return "relay"
        if "integrity_daemon" in joined:
            return "integrity_daemon"
        if "autonomous_ops.py" in joined:
            return "autonomous_ops"
        return f"proc-{len(calls)}"

    def _popen(args: List[str], **kwargs: object) -> DummyProcess:
        name = identify([str(part) for part in args])
        proc = DummyProcess(name)
        processes[name] = proc
        calls.append((name, [str(part) for part in args], dict(kwargs)))
        return proc

    monkeypatch.setattr("sentientos.runtime.shell.subprocess.Popen", _popen)
    return calls, processes


def test_runtime_shell_startup_order(monkeypatch: pytest.MonkeyPatch, runtime_config: Dict[str, object]) -> None:
    _patch_thread(monkeypatch)
    stub_cls = _patch_persona_loop(monkeypatch)
    calls, _ = _install_popen_stub(monkeypatch)

    shell = RuntimeShell(runtime_config)
    shell.start()

    assert [name for name, *_ in calls] == [
        "llama",
        "relay",
        "integrity_daemon",
        "autonomous_ops",
    ]
    assert shell.log_path == Path(runtime_config["runtime"]["root"]) / "logs" / "runtime.log"
    assert shell.runtime_root == Path(runtime_config["runtime"]["root"])
    assert isinstance(shell._persona_loop, stub_cls)
    assert shell._persona_loop.started is True

    expected_relay_args = [
        "python",
        "-m",
        "sentientos.oracle_relay",
        "--host",
        "127.0.0.1",
        "--port",
        "7000",
    ]
    assert calls[1][1] == expected_relay_args
    assert "creationflags" in calls[0][2]

    shell.shutdown()


def test_watchdog_restarts_process(monkeypatch: pytest.MonkeyPatch, runtime_config: Dict[str, object]) -> None:
    _patch_thread(monkeypatch)
    _patch_persona_loop(monkeypatch)
    calls, processes = _install_popen_stub(monkeypatch)

    shell = RuntimeShell(runtime_config)
    shell.start()
    relay_proc = processes["relay"]
    relay_proc.exit(1)

    shell.monitor_processes(run_once=True)

    assert [name for name, *_ in calls].count("relay") == 2
    assert isinstance(shell._processes["relay"], DummyProcess)
    shell.shutdown()


def test_config_loader_injects_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "SentientOS" / "sentientos_data" / "config" / "runtime.json"
    config = load_or_init_config(config_path)

    for key in DEFAULT_RUNTIME_CONFIG:
        assert key in config["runtime"]

    for key in ("enabled", "tick_interval_seconds", "max_message_length"):
        assert key in config["persona"]

    on_disk = json.loads(config_path.read_text(encoding="utf-8"))
    assert on_disk["runtime"]["windows_mode"] is True
    assert on_disk["persona"]["enabled"] is True

    dirs = ensure_runtime_dirs(config_path.parents[2])
    for expected in ("logs", "models", "config"):
        assert dirs[expected].exists()


def test_no_persona_dependency(monkeypatch: pytest.MonkeyPatch, runtime_config: Dict[str, object]) -> None:
    sys.modules.pop("sentientos.shell", None)
    _patch_thread(monkeypatch)
    _patch_persona_loop(monkeypatch)
    _, _ = _install_popen_stub(monkeypatch)
    shell = RuntimeShell(runtime_config)
    shell.start()
    assert "sentientos.shell" not in sys.modules
    shell.shutdown()


def test_persona_disabled_skips_loop(monkeypatch: pytest.MonkeyPatch, runtime_config: Dict[str, object]) -> None:
    runtime_config["persona"]["enabled"] = False
    _patch_thread(monkeypatch)
    _patch_persona_loop(monkeypatch)
    calls, _ = _install_popen_stub(monkeypatch)

    shell = RuntimeShell(runtime_config)
    shell.start()

    assert shell._persona_loop is None
    shell.shutdown()
    assert [name for name, *_ in calls] == [
        "llama",
        "relay",
        "integrity_daemon",
        "autonomous_ops",
    ]
