from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from queue import Queue

import pytest

import integration_dashboard
from integration_memory import configure_integration_root, integration_memory
from daemon import codex_daemon


@pytest.fixture(autouse=True)
def _reset_integration_root(tmp_path: Path):
    previous = integration_memory.root
    root = tmp_path / "integration"
    configure_integration_root(root)
    yield
    configure_integration_root(previous)


def _build_alert(daemon: str = "NetworkDaemon") -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = {
        "timestamp": timestamp,
        "source_daemon": daemon,
        "priority": "warning",
        "window_seconds": 600,
        "threshold": 5,
        "observed": 7,
        "event_type": "bandwidth_saturation",
        "name": "bandwidth_saturation",
    }
    return {
        "timestamp": timestamp,
        "source_daemon": "MonitoringDaemon",
        "event_type": "monitor_alert",
        "priority": "critical",
        "payload": payload,
    }


def test_integration_events_accumulate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "expand")
    monkeypatch.setattr(codex_daemon, "CODEX_CONFIRM_PATTERNS", [])
    monkeypatch.setattr(codex_daemon, "LOCAL_PEER_NAME", "local")
    monkeypatch.setattr(codex_daemon, "_requires_manual_confirmation", lambda files: False)
    monkeypatch.setattr(codex_daemon, "apply_patch", lambda diff_output: False)
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: True)

    sample_diff = """--- a/network_daemon.py\n+++ b/network_daemon.py\n@@\n- old\n+ new\n"""
    monkeypatch.setattr(
        codex_daemon._PredictiveRepairManager,
        "_invoke_codex",
        lambda self, prompt: sample_diff,
    )

    manager = codex_daemon._PredictiveRepairManager()
    queue: Queue = Queue()

    counts: list[int] = []
    for _ in range(3):
        manager.handle_alert(_build_alert(), queue)
        projection = integration_memory.project_state("NetworkDaemon", "bandwidth_saturation")
        counts.append(projection["count"])

    ledger_path = integration_memory.ledger_path
    contents = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 6, "three anomalies and three patch records expected"
    assert counts == sorted(counts), "risk counters should be monotonically increasing"
    assert counts[-1] >= 3, "history should escalate risk after repeated anomalies"


def test_dashboard_controls_reflect_integration_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "expand")
    monkeypatch.setattr(codex_daemon, "CODEX_CONFIRM_PATTERNS", [])
    monkeypatch.setattr(codex_daemon, "LOCAL_PEER_NAME", "local")
    monkeypatch.setattr(codex_daemon, "_requires_manual_confirmation", lambda files: False)
    monkeypatch.setattr(codex_daemon, "apply_patch", lambda diff_output: False)
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: True)

    sample_diff = """--- a/network_daemon.py\n+++ b/network_daemon.py\n@@\n- x\n+ y\n"""
    monkeypatch.setattr(
        codex_daemon._PredictiveRepairManager,
        "_invoke_codex",
        lambda self, prompt: sample_diff,
    )

    manager = codex_daemon._PredictiveRepairManager()
    queue: Queue = Queue()

    for _ in range(2):
        manager.handle_alert(_build_alert(), queue)

    panel = integration_dashboard.integration_panel_state(limit=5)
    assert panel.events, "panel should expose latest events"
    assert panel.projections, "panel should expose projections"
    assert panel.state_vectors, "state vectors should be summarized"

    first_entry = panel.events[0]["id"]
    integration_dashboard.lock_entry(first_entry)
    pruned = integration_dashboard.prune_entries(before=datetime.now(timezone.utc))
    assert pruned >= 1, "unlocked entries should be pruned"
    replayed = integration_dashboard.replay_entry(first_entry)
    assert replayed is not None and replayed.get("payload", {}).get("replay_of") == first_entry
    refreshed = integration_dashboard.integration_panel_state(limit=5)
    assert first_entry in refreshed.locked_entries
    assert any(event["id"] == replayed["id"] for event in refreshed.events)
