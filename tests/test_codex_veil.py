from __future__ import annotations

import json
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue

import pytest

from daemon import codex_daemon
from sentientos.daemons import pulse_bus
from sentientos.daemons.monitoring_daemon import MonitoringDaemon


class _DummyProcess:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _write_metrics(path: Path, daemon: str = "NetworkDaemon") -> None:
    now = datetime.now(timezone.utc)
    snapshots: list[dict[str, object]] = []
    for index in range(3):
        timestamp = (now - timedelta(minutes=index * 5)).isoformat()
        snapshots.append(
            {
                "timestamp": timestamp,
                "overall": {},
                "windows": {
                    "10m": {
                        "total_events": 6,
                        "per_daemon": {
                            daemon: {
                                "total": 6,
                                "priority": {"warning": 5, "critical": 1},
                                "event_type": {"bandwidth_saturation": 6},
                            }
                        },
                    }
                },
                "anomalies": [
                    {
                        "timestamp": timestamp,
                        "source_daemon": daemon,
                        "priority": "warning",
                        "window_seconds": 600,
                        "threshold": 5,
                        "observed": 7,
                        "event_type": "bandwidth_saturation",
                        "name": "bandwidth_saturation",
                    }
                ],
            }
        )
    payload = "\n".join(json.dumps(snapshot) for snapshot in snapshots) + "\n"
    path.write_text(payload, encoding="utf-8")


def _build_alert(daemon: str = "NetworkDaemon") -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "timestamp": timestamp,
        "source_daemon": "MonitoringDaemon",
        "event_type": "monitor_alert",
        "priority": "critical",
        "payload": {
            "timestamp": timestamp,
            "source_daemon": daemon,
            "priority": "warning",
            "window_seconds": 600,
            "threshold": 5,
            "observed": 7,
            "event_type": "bandwidth_saturation",
            "name": "bandwidth_saturation",
        },
    }


def _configure_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    suggestion_dir = tmp_path / "suggestions"
    log_path = tmp_path / "codex.jsonl"
    metrics_path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(codex_daemon, "CODEX_SUGGEST_DIR", suggestion_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_PATCH_DIR", suggestion_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_LOG", log_path)
    monkeypatch.setattr(codex_daemon, "MONITORING_METRICS_PATH", metrics_path)
    return metrics_path, suggestion_dir


def _collect_entries(queue: Queue) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    while not queue.empty():
        entries.append(queue.get())
    return entries


@pytest.fixture(autouse=True)
def reset_bus() -> None:
    pulse_bus.reset()
    yield
    pulse_bus.reset()


def test_local_predictive_patch_triggers_veil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metrics_path, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "expand")
    monkeypatch.setattr(codex_daemon, "load_ethics", lambda: "")

    sample_diff = """--- a/privilege.py\n+++ b/privilege.py\n@@\n- old\n+ new\n"""

    monkeypatch.setattr(codex_daemon.subprocess, "run", lambda *a, **k: _DummyProcess(sample_diff))

    apply_called = {"count": 0}

    def fake_apply(diff: str) -> bool:
        apply_called["count"] += 1
        return True

    monkeypatch.setattr(codex_daemon, "apply_patch", fake_apply)
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: True)

    published: list[dict[str, object]] = []

    def fake_publish(event: dict[str, object]) -> dict[str, object]:
        published.append(event)
        return event

    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", fake_publish)

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    _write_metrics(metrics_path)
    event = _build_alert()

    manager = codex_daemon._PredictiveRepairManager()
    ledger_queue: Queue = Queue()
    manager.handle_alert(event, ledger_queue)

    assert apply_called["count"] == 0

    entries = _collect_entries(ledger_queue)
    pending = [entry for entry in entries if entry.get("event") == "veil_pending"]
    assert pending and pending[0]["scope"] == "local"

    assert any(evt["event_type"] == "veil_request" for evt in published)

    metadata_files = list(suggestion_dir.glob("*.veil.json"))
    assert metadata_files, "veil metadata was not persisted"
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["scope"] == "local"
    assert metadata["requires_confirmation"] is True


def test_codex_cli_confirm_applies_patch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suggestion_dir = tmp_path / "suggestions"
    suggestion_dir.mkdir(parents=True, exist_ok=True)
    log_path = tmp_path / "codex.jsonl"

    monkeypatch.setattr(codex_daemon, "CODEX_SUGGEST_DIR", suggestion_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_LOG", log_path)

    patch_id = "predictive_123"
    diff_path = suggestion_dir / f"{patch_id}.diff"
    diff_content = "--- a/privilege.py\n+++ b/privilege.py\n@@\n- a\n+ b\n"
    diff_path.write_text(diff_content, encoding="utf-8")

    metadata_path = diff_path.with_suffix("").with_suffix(".veil.json")
    metadata = {
        "patch_id": patch_id,
        "patch_path": diff_path.as_posix().lstrip("/"),
        "scope": "local",
        "anomaly_pattern": "bandwidth_saturation",
        "requires_confirmation": True,
        "status": "pending",
        "files_changed": ["privilege.py"],
        "source_peer": "",
        "target_peer": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "codex_mode": "expand",
    }
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    apply_called = {"count": 0}

    def fake_apply(diff: str) -> bool:
        apply_called["count"] += 1
        assert diff == diff_content
        return True

    monkeypatch.setattr(codex_daemon, "apply_patch", fake_apply)
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: True)

    published: list[dict[str, object]] = []
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", lambda event: published.append(event) or event)

    monkeypatch.setattr("sentientos.privilege.require_admin_banner", lambda: None)
    monkeypatch.setattr("sentientos.privilege.require_lumos_approval", lambda: None)
    codex_cli = importlib.reload(importlib.import_module("sentientos.codex"))

    result = codex_cli.main(["confirm", patch_id])
    assert result == 0
    assert apply_called["count"] == 1

    log_entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert any(entry.get("event") == "veil_confirmed" for entry in log_entries)

    updated_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert updated_metadata["status"] == "confirmed"
    assert published and published[-1]["event_type"] == "veil_confirmed"


def test_codex_cli_reject_discards_patch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suggestion_dir = tmp_path / "suggestions"
    suggestion_dir.mkdir(parents=True, exist_ok=True)
    log_path = tmp_path / "codex.jsonl"

    monkeypatch.setattr(codex_daemon, "CODEX_SUGGEST_DIR", suggestion_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_LOG", log_path)

    patch_id = "predictive_456"
    diff_path = suggestion_dir / f"{patch_id}.diff"
    diff_path.write_text("--- a/file.py\n+++ b/file.py\n", encoding="utf-8")

    metadata_path = diff_path.with_suffix("").with_suffix(".veil.json")
    metadata = {
        "patch_id": patch_id,
        "patch_path": diff_path.as_posix().lstrip("/"),
        "scope": "local",
        "anomaly_pattern": "bandwidth_saturation",
        "requires_confirmation": True,
        "status": "pending",
        "files_changed": ["file.py"],
        "source_peer": "",
        "target_peer": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "codex_mode": "expand",
    }
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    monkeypatch.setattr(codex_daemon, "apply_patch", lambda diff: pytest.fail("should not apply"))
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: True)

    published: list[dict[str, object]] = []
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", lambda event: published.append(event) or event)

    monkeypatch.setattr("sentientos.privilege.require_admin_banner", lambda: None)
    monkeypatch.setattr("sentientos.privilege.require_lumos_approval", lambda: None)
    codex_cli = importlib.reload(importlib.import_module("sentientos.codex"))

    result = codex_cli.main(["reject", patch_id])
    assert result == 0

    assert not diff_path.exists(), "diff should be removed after rejection"
    updated_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert updated_metadata["status"] == "rejected"
    assert published and published[-1]["event_type"] == "veil_rejected"


def test_federated_sensitive_patch_creates_veil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(codex_daemon, "LOCAL_PEER_NAME", "peer-beta")
    monkeypatch.setattr(codex_daemon, "FEDERATED_AUTO_APPLY", True)

    apply_called = {"count": 0}

    def fake_apply(diff: str) -> bool:
        apply_called["count"] += 1
        return True

    monkeypatch.setattr(codex_daemon, "apply_patch", fake_apply)
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: True)

    published: list[dict[str, object]] = []
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", lambda event: published.append(event) or event)

    ledger_queue: Queue = Queue()
    sample_diff = """--- a/privilege.py\n+++ b/privilege.py\n@@\n- a\n+ b\n"""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "CodexDaemon",
        "event_type": "predictive_suggestion",
        "source_peer": "peer-alpha",
        "payload": {
            "source_peer": "peer-alpha",
            "target_peer": "peer-beta",
            "target_daemon": "NetworkDaemon",
            "anomaly_pattern": "bandwidth_saturation",
            "patch_path": "peer-alpha.diff",
            "status": "suggested",
            "analysis_window": "10m",
            "triggering_anomaly": {"event_type": "bandwidth_saturation"},
            "patch_diff": sample_diff,
        },
    }

    codex_daemon._process_predictive_suggestion(event, ledger_queue)

    assert apply_called["count"] == 0
    entries = _collect_entries(ledger_queue)
    pending = [entry for entry in entries if entry.get("event") == "veil_pending"]
    assert pending and pending[0]["scope"] == "federated"

    metadata_files = list(suggestion_dir.glob("*.veil.json"))
    assert metadata_files
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["scope"] == "federated"
    assert metadata["target_peer"] == "peer-beta"
    assert any(evt["event_type"] == "veil_request" for evt in published)


def test_monitoring_daemon_surfaces_pending_veil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    glow_root = tmp_path / "glow" / "monitoring"
    glow_root.mkdir(parents=True, exist_ok=True)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MONITORING_GLOW_ROOT", str(glow_root))
    monkeypatch.delenv("MONITORING_METRICS_PATH", raising=False)
    monkeypatch.delenv("MONITORING_ALERTS_PATH", raising=False)
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(logs_dir))

    monitor = MonitoringDaemon(snapshot_interval=timedelta(0))
    try:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "CodexDaemon",
            "event_type": "veil_request",
            "priority": "warning",
            "payload": {
                "patch_id": "predictive_veil",
                "patch_path": "glow/codex_suggestions/predictive_veil.diff",
                "scope": "federated",
                "anomaly_pattern": "bandwidth_saturation",
                "requires_confirmation": True,
                "source_peer": "peer-alpha",
                "target_peer": "peer-beta",
            },
        }
        monitor._handle_event(event)

        metrics = monitor.current_metrics()
        assert metrics["veil_pending"] and metrics["veil_pending"][0]["patch_id"] == "predictive_veil"

        resolution = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "CodexDaemon",
            "event_type": "veil_confirmed",
            "priority": "info",
            "payload": {"patch_id": "predictive_veil"},
        }
        monitor._handle_event(resolution)

        cleared = monitor.current_metrics()["veil_pending"]
        assert cleared == []
    finally:
        monitor.stop()
