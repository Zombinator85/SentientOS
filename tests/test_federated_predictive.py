"""Federated predictive healing flows."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from queue import Queue
from typing import List

import pytest

from daemon import codex_daemon
from sentientos.daemons import pulse_bus


class _DummyProcess:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _write_metrics(path, daemon: str = "NetworkDaemon") -> None:
    now = datetime.now(timezone.utc)
    snapshots: List[dict[str, object]] = []
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


def _configure_paths(monkeypatch: pytest.MonkeyPatch, tmp_path):
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


def _build_remote_alert(peer: str = "peer-alpha", daemon: str = "NetworkDaemon") -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "timestamp": timestamp,
        "source_daemon": "MonitoringDaemon",
        "event_type": "monitor_alert",
        "priority": "critical",
        "source_peer": peer,
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


def test_remote_anomaly_emits_federated_suggestion(tmp_path, monkeypatch):
    metrics_path, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    pulse_bus.reset()
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "observe")
    monkeypatch.setattr(codex_daemon, "CODEX_CONFIRM_PATTERNS", ["/vow/"])
    monkeypatch.setattr(codex_daemon, "LOCAL_PEER_NAME", "peer-beta")
    monkeypatch.setattr(codex_daemon, "FEDERATED_AUTO_APPLY", False)
    monkeypatch.setattr(codex_daemon, "load_ethics", lambda: "")

    sample_diff = """--- a/network_daemon.py\n+++ b/network_daemon.py\n@@\n- old\n+ new\n"""

    def fake_codex(cmd, capture_output=False, text=False, input=None):
        return _DummyProcess(sample_diff)

    published: list[dict] = []

    def fake_publish(event):
        published.append(event)
        return event

    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_codex)
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", fake_publish)

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    _write_metrics(metrics_path)
    event = _build_remote_alert()

    manager = codex_daemon._PredictiveRepairManager()
    ledger_queue: Queue = Queue()
    manager.handle_alert(event, ledger_queue)

    assert any(path.name.startswith("predictive_peer-alpha_") for path in suggestion_dir.glob("*.diff"))

    assert published, "predictive suggestion should be published to federation"
    suggestion = published[0]
    assert suggestion["event_type"] == "predictive_suggestion"
    payload = suggestion["payload"]
    assert payload["status"] == "suggested"
    assert payload["target_peer"] == "peer-alpha"
    assert payload["source_peer"] == "peer-beta"
    assert payload["target_daemon"] == "NetworkDaemon"

    entries = _collect_entries(ledger_queue)
    assert any(entry.get("event") == "federated_predictive_event" for entry in entries)


def test_peer_suggestion_logged_locally(tmp_path, monkeypatch):
    _, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    pulse_bus.reset()
    monkeypatch.setattr(codex_daemon, "LOCAL_PEER_NAME", "peer-beta")
    monkeypatch.setattr(codex_daemon, "FEDERATED_AUTO_APPLY", False)

    ledger_queue: Queue = Queue()
    sample_diff = """--- a/network_daemon.py\n+++ b/network_daemon.py\n@@\n- a\n+ b\n"""
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
            "patch_path": "predictive_peer-alpha.diff",
            "status": "suggested",
            "analysis_window": "10m",
            "triggering_anomaly": {"event_type": "bandwidth_saturation"},
            "patch_diff": sample_diff,
        },
    }

    codex_daemon._process_predictive_suggestion(event, ledger_queue)

    stored = sorted(suggestion_dir.glob("peer_*.diff"))
    assert stored, "peer suggestion diff should be stored"
    contents = stored[-1].read_text(encoding="utf-8")
    assert sample_diff.strip() in contents

    entries = _collect_entries(ledger_queue)
    recorded = [entry for entry in entries if entry.get("event") == "federated_predictive_event"]
    assert recorded and recorded[0]["status"] == "suggested"
    assert recorded[0]["source_peer"] == "peer-alpha"
    assert recorded[0]["target_daemon"] == "NetworkDaemon"


def test_auto_apply_runs_when_enabled(tmp_path, monkeypatch):
    _, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    pulse_bus.reset()
    monkeypatch.setattr(codex_daemon, "LOCAL_PEER_NAME", "peer-beta")
    monkeypatch.setattr(codex_daemon, "FEDERATED_AUTO_APPLY", True)

    applied = {"count": 0}
    verified = {"count": 0}
    published: list[dict] = []

    def fake_apply(diff: str) -> bool:
        applied["count"] += 1
        return True

    def fake_ci(queue: Queue) -> bool:
        verified["count"] += 1
        return True

    def fake_publish(event):
        published.append(event)
        return event

    monkeypatch.setattr(codex_daemon, "apply_patch", fake_apply)
    monkeypatch.setattr(codex_daemon, "run_ci", fake_ci)
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", fake_publish)

    ledger_queue: Queue = Queue()
    sample_diff = """--- a/network_daemon.py\n+++ b/network_daemon.py\n@@\n- a\n+ b\n"""
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
            "patch_path": "predictive_peer-alpha.diff",
            "status": "suggested",
            "analysis_window": "10m",
            "triggering_anomaly": {"event_type": "bandwidth_saturation"},
            "patch_diff": sample_diff,
        },
    }

    codex_daemon._process_predictive_suggestion(event, ledger_queue)

    assert applied["count"] == 1
    assert verified["count"] == 1
    assert published, "auto apply should publish confirmation"
    assert published[-1]["payload"]["status"] == "applied"

    entries = _collect_entries(ledger_queue)
    statuses = [entry["status"] for entry in entries if entry.get("event") == "federated_predictive_event"]
    assert "suggested" in statuses and "applied" in statuses


def test_privileged_paths_are_rejected(tmp_path, monkeypatch):
    _, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    pulse_bus.reset()
    monkeypatch.setattr(codex_daemon, "LOCAL_PEER_NAME", "peer-beta")
    monkeypatch.setattr(codex_daemon, "FEDERATED_AUTO_APPLY", True)

    ledger_queue: Queue = Queue()
    restricted_diff = """--- a/vow/config.yaml\n+++ b/vow/config.yaml\n@@\n- guard\n+ adjust\n"""
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
            "patch_path": "predictive_peer-alpha.diff",
            "status": "suggested",
            "analysis_window": "10m",
            "triggering_anomaly": {"event_type": "bandwidth_saturation"},
            "patch_diff": restricted_diff,
        },
    }

    codex_daemon._process_predictive_suggestion(event, ledger_queue)

    assert not any(suggestion_dir.glob("peer_*.diff")), "restricted diffs should not be stored"
    entries = _collect_entries(ledger_queue)
    rejected = [entry for entry in entries if entry.get("status") == "rejected"]
    assert rejected and rejected[0]["source_peer"] == "peer-alpha"

