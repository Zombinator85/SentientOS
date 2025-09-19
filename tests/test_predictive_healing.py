"""Tests for Codex predictive self-healing integrations."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from queue import Queue
from typing import List

import pytest

from daemon import codex_daemon


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
                                "matrix": {
                                    "warning": {"bandwidth_saturation": 5},
                                    "critical": {"bandwidth_saturation": 1},
                                },
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


def test_predictive_analysis_triggers_on_recurring_anomaly(tmp_path, monkeypatch):
    metrics_path, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "observe")
    monkeypatch.setattr(codex_daemon, "CODEX_CONFIRM_PATTERNS", ["/vow/"])
    monkeypatch.setattr(codex_daemon, "load_ethics", lambda: "Sanctuary Safety")

    sample_diff = """--- a/network_daemon.py\n+++ b/network_daemon.py\n@@\n- old\n+ new\n"""
    captured_prompts: list[str] = []

    def fake_codex(cmd, capture_output=False, text=False, input=None):
        assert cmd[:2] == ["codex", "exec"]
        captured_prompts.append(cmd[2])
        return _DummyProcess(sample_diff)

    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_codex)
    monkeypatch.setattr(codex_daemon, "apply_patch", lambda diff: True)
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: True)

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    _write_metrics(metrics_path)
    event = _build_alert()

    manager = codex_daemon._PredictiveRepairManager()
    ledger_queue: Queue = Queue()
    manager.handle_alert(event, ledger_queue)

    suggestions = sorted(suggestion_dir.glob("predictive_*.diff"))
    assert suggestions, "predictive diff was not written"
    assert captured_prompts and "Safety Context" in captured_prompts[0]

    entries = _collect_entries(ledger_queue)
    assert any(entry["event"] == "self_predict_suggested" for entry in entries)
    assert not any(entry["event"] == "self_predict_applied" for entry in entries)
    suggested = next(entry for entry in entries if entry["event"] == "self_predict_suggested")
    assert suggested["status"] == "suggested"
    assert suggested["analysis_window"] in {"10m", "600s"}


def test_predictive_auto_apply_runs_in_expand_mode(tmp_path, monkeypatch):
    metrics_path, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "expand")
    monkeypatch.setattr(codex_daemon, "load_ethics", lambda: "")

    sample_diff = """--- a/network_daemon.py\n+++ b/network_daemon.py\n@@\n- a\n+ b\n"""

    def fake_codex(cmd, capture_output=False, text=False, input=None):
        return _DummyProcess(sample_diff)

    apply_called = {"count": 0}
    run_ci_called = {"count": 0}

    def fake_apply(diff: str) -> bool:
        apply_called["count"] += 1
        return True

    def fake_run_ci(queue: Queue) -> bool:
        run_ci_called["count"] += 1
        return True

    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_codex)
    monkeypatch.setattr(codex_daemon, "apply_patch", fake_apply)
    monkeypatch.setattr(codex_daemon, "run_ci", fake_run_ci)

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    _write_metrics(metrics_path)
    event = _build_alert()

    manager = codex_daemon._PredictiveRepairManager()
    ledger_queue: Queue = Queue()
    manager.handle_alert(event, ledger_queue)

    entries = _collect_entries(ledger_queue)
    assert any(entry["event"] == "self_predict_applied" for entry in entries)
    applied_entry = next(entry for entry in entries if entry["event"] == "self_predict_applied")
    assert applied_entry["verification_result"] is True
    assert apply_called["count"] == 1
    assert run_ci_called["count"] == 1


def test_predictive_auto_apply_respects_confirm_patterns(tmp_path, monkeypatch):
    metrics_path, suggestion_dir = _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "expand")
    monkeypatch.setattr(codex_daemon, "load_ethics", lambda: "")

    restricted_diff = """--- a/vow/config.yaml\n+++ b/vow/config.yaml\n@@\n- guard\n+ adjust\n"""

    def fake_codex(cmd, capture_output=False, text=False, input=None):
        return _DummyProcess(restricted_diff)

    apply_called = {"count": 0}

    def fake_apply(diff: str) -> bool:
        apply_called["count"] += 1
        return True

    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_codex)
    monkeypatch.setattr(codex_daemon, "apply_patch", fake_apply)
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: True)

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    _write_metrics(metrics_path)
    event = _build_alert()

    manager = codex_daemon._PredictiveRepairManager()
    ledger_queue: Queue = Queue()
    manager.handle_alert(event, ledger_queue)

    entries = _collect_entries(ledger_queue)
    assert any(entry["event"] == "self_predict_suggested" for entry in entries)
    assert not any(entry["event"] == "self_predict_applied" for entry in entries)
    assert apply_called["count"] == 0

    suggestions = sorted(suggestion_dir.glob("predictive_*.diff"))
    assert suggestions, "predictive diff missing"
    assert "Predictive patch rejected" in suggestions[-1].read_text(encoding="utf-8")
