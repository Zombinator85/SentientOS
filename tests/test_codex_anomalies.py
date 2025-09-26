from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from codex import (
    AnomalyCoordinator,
    AnomalyDetector,
    AnomalyEmitter,
    LedgerInterface,
    PatchStorage,
    ProposalPlan,
    RewriteDashboard,
    RewriteProposalEngine,
    ScopedRewriteEngine,
)


class DummyLedger(LedgerInterface):
    def __init__(self, verdicts: list[bool]) -> None:
        self._verdicts = deque(verdicts)

    def verify_patch(self, patch):  # type: ignore[override]
        if not self._verdicts:
            return False
        return self._verdicts.popleft()


@dataclass
class ManualClock:
    moment: datetime

    def tick(self, delta: timedelta) -> None:
        self.moment += delta

    def now(self) -> datetime:
        return self.moment


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_anomaly_pipeline_generates_guarded_proposals(tmp_path: Path) -> None:
    crash_path = _write(tmp_path / "daemons" / "healer.py", "cooldown = 1\n")
    latency_path = _write(tmp_path / "daemons" / "pulse.py", "LATENCY_BUDGET = 200\n")
    ledger_path = _write(tmp_path / "daemons" / "ledger.py", "SYNC_REQUIRED = False\n")
    orphan_path = _write(tmp_path / "daemons" / "tasks.py", "ORPHAN_GUARD = False\n")

    logs = [
        {"daemon": "HealingDaemon", "event": "crash"},
        {"daemon": "HealingDaemon", "event": "crash"},
        {"daemon": "HealingDaemon", "event": "crash"},
    ]
    pulses = [
        {"daemon": "PulseDaemon", "latency_ms": 1_500, "expected_latency_ms": 400},
    ]
    backlog = [
        {"daemon": "LedgerDaemon", "ledger_mismatch": True, "task_id": "ledger-1"},
        {"daemon": "TaskDaemon", "status": "orphaned", "task_id": "task-77"},
    ]

    clock = ManualClock(moment=datetime(2025, 1, 1, tzinfo=timezone.utc))
    ledger = DummyLedger([False, False, False, False])
    storage = PatchStorage(tmp_path / "glow" / "proposals", tmp_path / "daemon" / "quarantine")
    engine = ScopedRewriteEngine(ledger, storage=storage, cooldown=timedelta(seconds=0), now=clock.now)

    published_events: list[dict[str, object]] = []
    emitter = AnomalyEmitter(
        tmp_path / "pulse" / "anomalies",
        bus=SimpleNamespace(publish=lambda event: published_events.append(event)),
    )
    detector = AnomalyDetector(
        crash_threshold=3,
        latency_threshold_ms=800,
        backlog_threshold=5,
        now=clock.now,
    )
    proposal_engine = RewriteProposalEngine(engine, emitter=emitter)

    plans = {
        "crash_loop": ProposalPlan(
            daemon="HealingDaemon",
            target_path=crash_path,
            builder=lambda path, anomaly: path.read_text(encoding="utf-8").replace("cooldown = 1", "cooldown = 3"),
            reason="Increase cooldown to break crash loop",
            confidence=0.8,
            urgency="high",
        ),
        "latency_spike": ProposalPlan(
            daemon="PulseDaemon",
            target_path=latency_path,
            builder=lambda path, anomaly: path.read_text(encoding="utf-8").replace("200", "400"),
            reason="Expand latency budget",
            confidence=0.6,
        ),
        "ledger_mismatch": ProposalPlan(
            daemon="LedgerDaemon",
            target_path=ledger_path,
            builder=lambda path, anomaly: path.read_text(encoding="utf-8").replace("False", "True"),
            reason="Force ledger resynchronization",
            confidence=0.7,
        ),
        "orphaned_tasks": ProposalPlan(
            daemon="TaskDaemon",
            target_path=orphan_path,
            builder=lambda path, anomaly: path.read_text(encoding="utf-8").replace("False", "True"),
            reason="Reclaim orphaned tasks",
            confidence=0.65,
        ),
    }

    coordinator = AnomalyCoordinator(detector, proposal_engine)
    patches = coordinator.evaluate(logs, pulses, backlog, plans)

    assert len(patches) == 4
    assert all(patch.status == "pending" for patch in patches)

    # Suggestions should not mutate source files.
    assert crash_path.read_text(encoding="utf-8") == "cooldown = 1\n"
    assert latency_path.read_text(encoding="utf-8") == "LATENCY_BUDGET = 200\n"
    assert ledger_path.read_text(encoding="utf-8") == "SYNC_REQUIRED = False\n"
    assert orphan_path.read_text(encoding="utf-8") == "ORPHAN_GUARD = False\n"

    # Proposals are persisted under /glow/proposals.
    for patch in patches:
        proposal_dir = storage.base_dir / patch.patch_id  # type: ignore[attr-defined]
        assert (proposal_dir / "patch.json").exists()

    dashboard = RewriteDashboard(storage)
    rows = {row["patch_id"]: row for row in dashboard.rows()}
    assert set(rows) == {patch.patch_id for patch in patches}
    for patch in patches:
        entry = rows[patch.patch_id]
        assert entry["anomaly_description"]
        assert entry["confidence"] == pytest.approx(patch.confidence)
        assert entry["actions"]["approve"] is True

    log_path = tmp_path / "pulse" / "anomalies" / f"{clock.now().date().isoformat()}.jsonl"
    assert log_path.exists(), "Anomaly emitter should persist events"
    payloads = [json.loads(line) for line in log_path.read_text(encoding="utf-8").strip().splitlines()]
    assert len(payloads) == 4
    assert {entry["patch_id"] for entry in payloads} == set(rows)

    assert len(published_events) == 4
    assert all(event["event_type"] == "anomaly_detected" for event in published_events)

    # Ledger gating denies auto-application and sends proposals to quarantine.
    engine.process_pending()
    assert crash_path.read_text(encoding="utf-8") == "cooldown = 1\n"
    assert latency_path.read_text(encoding="utf-8") == "LATENCY_BUDGET = 200\n"
    quarantine_root = tmp_path / "daemon" / "quarantine"
    assert quarantine_root.exists()
    quarantined_ids = {entry.name for entry in quarantine_root.iterdir()}
    assert quarantined_ids == {patch.patch_id for patch in patches}
