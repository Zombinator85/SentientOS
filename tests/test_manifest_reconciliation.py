from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue

import pytest

from daemon import codex_daemon
from sentientos import immutability
from sentientos.daemons.monitoring_daemon import MonitoringDaemon


class _DummyProcess:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def test_self_repair_reconciles_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = tmp_path / "immutable_manifest.json"
    suggestion_dir = tmp_path / "suggestions"
    reasoning_dir = tmp_path / "reason"
    patch_dir = tmp_path / "patches"
    suggestion_dir.mkdir(parents=True, exist_ok=True)
    reasoning_dir.mkdir(parents=True, exist_ok=True)
    patch_dir.mkdir(parents=True, exist_ok=True)

    target_file = tmp_path / "module.py"
    target_file.write_text("old\n", encoding="utf-8")

    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "repair")
    monkeypatch.setattr(codex_daemon, "CODEX_MAX_ITERATIONS", 1)
    monkeypatch.setattr(codex_daemon, "CODEX_SUGGEST_DIR", suggestion_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_PATCH_DIR", patch_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_REASONING_DIR", reasoning_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_LOG", tmp_path / "codex.log")
    monkeypatch.setattr(codex_daemon, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(codex_daemon, "MANIFEST_AUTO_UPDATE", True)

    immutability.reset_key_cache()

    diff_text = """--- a/module.py\n+++ b/module.py\n@@\n- old\n+ new\n"""

    def fake_subprocess_run(cmd, *args, **kwargs):  # type: ignore[override]
        if cmd[:2] == ["codex", "exec"]:
            return _DummyProcess(diff_text)
        return _DummyProcess()

    diagnostic_calls = {"count": 0}

    def fake_run_diagnostics():
        if diagnostic_calls["count"] == 0:
            diagnostic_calls["count"] += 1
            return False, "FAILED tests/test_example.py::test_case\n", 1
        diagnostic_calls["count"] += 1
        return True, "1 passed\n", 0

    def fake_apply_patch(diff: str, label: str | None = None) -> dict[str, object]:
        target_file.write_text("new\n", encoding="utf-8")
        return {"applied": True, "archived_diff": None, "restored_repo": False, "failure_reason": None}

    published: list[dict[str, object]] = []

    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(codex_daemon, "run_diagnostics", fake_run_diagnostics)
    monkeypatch.setattr(codex_daemon, "_call_apply_patch", fake_apply_patch)
    monkeypatch.setattr(codex_daemon, "log_activity", lambda entry: None)
    monkeypatch.setattr(codex_daemon, "send_notifications", lambda entry: None)
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", lambda event: published.append(event) or event)

    ledger_queue: Queue = Queue()
    result = codex_daemon.run_once(ledger_queue)
    assert result is not None
    assert result.get("event") == "self_repair"

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "module.py" in data["files"]
    assert data["files"]["module.py"]["sha256"]
    assert immutability.verify_manifest_signature(data)

    entries = list(ledger_queue.queue)
    assert any(entry.get("event") == "manifest_reconciled" for entry in entries)
    manifest_entry = next(entry for entry in entries if entry.get("event") == "manifest_reconciled")
    assert manifest_entry["source_event"] == "self_repair"

    assert published and published[-1]["event_type"] == "manifest_update"
    assert "module.py" in published[-1]["payload"].get("files", [])


def test_veil_confirmation_updates_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = tmp_path / "immutable_manifest.json"
    veil_file = tmp_path / "veil.py"
    veil_file.write_text("veil=1\n", encoding="utf-8")

    monkeypatch.setattr(codex_daemon, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(codex_daemon, "MANIFEST_AUTO_UPDATE", True)
    immutability.reset_key_cache()

    published: list[dict[str, object]] = []
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", lambda event: published.append(event) or event)

    ledger_queue: Queue = Queue()
    codex_daemon.record_veil_confirmed(["veil.py"], ledger_queue)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "veil.py" in data["files"]
    assert immutability.verify_manifest_signature(data)

    entries = list(ledger_queue.queue)
    assert any(entry.get("event") == "manifest_reconciled" for entry in entries)
    resolved = next(entry for entry in entries if entry.get("event") == "manifest_reconciled")
    assert resolved["source_event"] == "veil_confirmed"

    assert published and published[-1]["event_type"] == "manifest_update"
    assert "veil.py" in published[-1]["payload"].get("files", [])


def test_manifest_reconciliation_respects_manual_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = tmp_path / "immutable_manifest.json"
    skip_file = tmp_path / "skip.py"
    skip_file.write_text("skip=1\n", encoding="utf-8")

    monkeypatch.setattr(codex_daemon, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(codex_daemon, "MANIFEST_AUTO_UPDATE", False)
    immutability.reset_key_cache()

    published: list[dict[str, object]] = []
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", lambda event: published.append(event) or event)

    ledger_queue: Queue = Queue()
    codex_daemon.record_self_predict_applied(["skip.py"], ledger_queue)

    assert not manifest_path.exists()
    assert ledger_queue.empty()
    assert not published


def test_monitoring_captures_manifest_updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    glow_root = tmp_path / "glow"
    logs_root = tmp_path / "logs"
    glow_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MONITORING_GLOW_ROOT", str(glow_root))
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(logs_root))

    monitor = MonitoringDaemon(snapshot_interval=timedelta(0))
    try:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "CodexDaemon",
            "event_type": "manifest_update",
            "priority": "info",
            "payload": {
                "files": ["module.py"],
                "signature": "sig",
                "manifest_path": "immutable_manifest.json",
                "source_event": "self_repair",
            },
        }
        monitor._handle_event(event)
        metrics = monitor.current_metrics()
        assert metrics["manifest_updates"]
        latest = metrics["manifest_updates"][0]
        assert latest["files"] == ["module.py"]

        snapshot = monitor.persist_snapshot()
        assert snapshot["manifest_updates"]
    finally:
        monitor.stop()
