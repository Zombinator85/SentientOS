from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import json

import pytest

from codex import (
    Anomaly,
    IntentEmitter,
    IntentPrioritizer,
    PriorityScoringEngine,
    PriorityWeights,
    RewriteDashboard,
)
from codex.rewrites import PatchStorage, RewritePatch


def _now() -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


def _build_patch(
    storage: PatchStorage,
    target: Path,
    *,
    patch_id: str,
    daemon: str,
    urgency: str,
    confidence: float,
    metadata: dict,
) -> RewritePatch:
    original = "cooldown = 1\n"
    modified = "cooldown = 3\n"
    diff = "\n".join([
        "--- a/cooldown.py",
        "+++ b/cooldown.py",
        "@@",
        "-cooldown = 1",
        "+cooldown = 3",
    ])
    patch = RewritePatch(
        patch_id=patch_id,
        daemon=daemon,
        target_path=str(target),
        timestamp=_now(),
        diff=diff,
        original_content=original,
        modified_content=modified,
        reason="Increase cooldown",
        confidence=confidence,
        urgency=urgency,
        metadata=metadata,
        source="codex",
    )
    storage.save_patch(patch)
    return patch


def test_priority_engine_emits_intent_and_updates_dashboard(tmp_path: Path) -> None:
    # Prepare rewrite storage
    storage = PatchStorage(tmp_path / "glow" / "patches", tmp_path / "daemon" / "quarantine")
    target_a = tmp_path / "daemons" / "daemon_a.py"
    target_a.parent.mkdir(parents=True, exist_ok=True)
    target_a.write_text("cooldown = 1\n", encoding="utf-8")
    target_b = tmp_path / "daemons" / "daemon_b.py"
    target_b.write_text("cooldown = 1\n", encoding="utf-8")

    patch_a = _build_patch(
        storage,
        target_a,
        patch_id="patch-a",
        daemon="DaemonA",
        urgency="high",
        confidence=0.7,
        metadata={
            "anomaly": {
                "severity": "warning",
                "impact": "daemon",
                "count": 2,
                "description": "Latency drift",
            }
        },
    )
    patch_b = _build_patch(
        storage,
        target_b,
        patch_id="patch-b",
        daemon="DaemonB",
        urgency="medium",
        confidence=0.9,
        metadata={
            "anomaly": {
                "severity": "high",
                "impact": "local",
                "count": 1,
                "description": "Backlog drift",
            }
        },
    )

    anomalies = [
        Anomaly(
            kind="latency_drift",
            description="Daemon Y latency drift",
            severity="warning",
            metadata={"daemon": "DaemonY", "impact": "local", "confidence": 0.6},
        ),
        Anomaly(
            kind="cooldown_breach",
            description="Daemon X cooldown breach",
            severity="critical",
            metadata={"daemon": "DaemonX", "impact": "daemon", "confidence": 0.9},
        ),
        Anomaly(
            kind="latency_drift",
            description="Daemon Y latency drift",
            severity="warning",
            metadata={"daemon": "DaemonY", "impact": "local", "confidence": 0.6},
        ),
    ]

    payloads: list[dict[str, object]] = []
    emitter = IntentEmitter(tmp_path / "pulse" / "intent", bus=SimpleNamespace(publish=lambda data: payloads.append(data)), now=_now)
    scoring = PriorityScoringEngine(weights=PriorityWeights(0.45, 0.2, 0.2, 0.15))
    prioritizer = IntentPrioritizer(scoring, emitter=emitter, integration_log=tmp_path / "integration" / "intent_log.jsonl", now=_now)

    intent = prioritizer.evaluate(anomalies, [patch_a, patch_b])
    assert intent is not None
    assert intent.candidate_id.startswith("anomaly:cooldown_breach")
    assert intent.label == "Daemon X cooldown breach"

    # Intent file and bus payload should reflect the choice.
    intent_path = tmp_path / "pulse" / "intent" / "current.json"
    payload = json.loads(intent_path.read_text(encoding="utf-8"))
    assert payload["intent"]["id"] == intent.candidate_id
    assert "Codex intends to prioritize" in payload["message"]
    assert payloads and payloads[-1]["intent"]["id"] == intent.candidate_id

    # Dashboard rows expose the priority metadata for rewrite patches.
    dashboard = RewriteDashboard(storage, intent_layer=prioritizer)
    rows = {row["patch_id"]: row for row in dashboard.rows()}
    assert "patch-a" in rows and "patch-b" in rows
    assert rows["patch-a"]["intent"]["score"] == pytest.approx(prioritizer.get_candidate("rewrite:patch-a").score)

    # Store initial score for learning comparison.
    initial_scores = {candidate.candidate_id: candidate.score for candidate in prioritizer.candidates}

    # Operator overrides a different patch.
    prioritizer.override("rewrite:patch-a")
    overridden_intent = prioritizer.evaluate(anomalies, [patch_a, patch_b])
    assert overridden_intent is not None
    assert overridden_intent.candidate_id == "rewrite:patch-a"

    prioritizer.lock_current()

    # Introduce a new high severity anomaly; lock should keep override intent active.
    new_anomaly = Anomaly(
        kind="integration_failure",
        description="Daemon Z integration failure",
        severity="critical",
        metadata={"daemon": "DaemonZ", "impact": "system", "confidence": 0.95},
    )
    prioritizer.evaluate(anomalies + [new_anomaly], [patch_a, patch_b])
    assert prioritizer.current_intent is not None
    assert prioritizer.current_intent.candidate_id == "rewrite:patch-a"

    prioritizer.unlock()
    prioritizer.clear_override()

    # After learning from overrides, patch-a should receive a boosted score.
    prioritizer.evaluate(anomalies + [new_anomaly], [patch_a, patch_b])
    boosted_candidate = prioritizer.get_candidate("rewrite:patch-a")
    assert boosted_candidate is not None
    assert boosted_candidate.score > initial_scores["rewrite:patch-a"]

    prioritizer.acknowledge()
    prioritizer.evaluate(anomalies + [new_anomaly], [patch_a, patch_b])
    assert prioritizer.current_intent is not None and prioritizer.current_intent.acknowledged

    # Fulfilled intents are appended to integration log.
    log_path = prioritizer.fulfill(result="applied")
    contents = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert contents and contents[-1]["result"] == "applied"


def test_operator_acknowledge_and_integration_events(tmp_path: Path) -> None:
    storage = PatchStorage(tmp_path / "glow" / "patches", tmp_path / "daemon" / "quarantine")
    target = tmp_path / "daemons" / "daemon_c.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("cooldown = 1\n", encoding="utf-8")

    patch = _build_patch(
        storage,
        target,
        patch_id="patch-c",
        daemon="DaemonC",
        urgency="medium",
        confidence=0.55,
        metadata={"impact": "local"},
    )

    scoring = PriorityScoringEngine()
    emitter = IntentEmitter(tmp_path / "pulse" / "intent", now=_now)
    prioritizer = IntentPrioritizer(scoring, emitter=emitter, integration_log=tmp_path / "integration" / "intent_log.jsonl", now=_now)

    integrations = [
        {"id": "sync_retry", "severity": "high", "impact": "service", "confidence": 0.8, "description": "Sync retry loop"},
        {"id": "sync_retry", "severity": "high", "impact": "service", "confidence": 0.8, "description": "Sync retry loop"},
        {"id": "audit_gap", "severity": "warning", "impact": "daemon", "confidence": 0.5, "description": "Audit gap"},
    ]

    prioritizer.evaluate([], [patch], integrations)
    assert prioritizer.current_intent is not None
    assert prioritizer.current_intent.candidate_id.startswith("integration:sync_retry")

    prioritizer.acknowledge()
    prioritizer.evaluate([], [patch], integrations)
    assert prioritizer.current_intent is not None and prioritizer.current_intent.acknowledged

    payload = json.loads((tmp_path / "pulse" / "intent" / "current.json").read_text(encoding="utf-8"))
    assert payload["intent"]["acknowledged"] is True

