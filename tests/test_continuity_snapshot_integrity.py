from __future__ import annotations

import json

import pytest

from sentientos.autonomy.state import (
    ContinuitySnapshot,
    ContinuityStateManager,
    SnapshotDivergenceError,
    canonicalise_continuity_snapshot,
    continuity_snapshot_digest,
)
from sentientos.gradient_contract import GradientInvariantViolation


def test_continuity_snapshot_roundtrip_enforces_digest(tmp_path):
    path = tmp_path / "session.json"
    manager = ContinuityStateManager(path)
    snapshot = ContinuitySnapshot(
        mood="present",
        readiness={"summary": {"healthy": True}},
        curiosity_queue=[{"goal": {"id": "g-1"}, "source": "ocr"}],
        curiosity_inflight=[{"goal": {"id": "g-2"}, "source": "asr"}],
        last_readiness_ts="2025-01-01T00:00:00+00:00",
    )

    manager.save(snapshot)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert "digest" in stored and stored["digest"]
    assert "snapshot" in stored

    restored = manager.load()
    assert restored.mood == "present"
    assert restored.readiness == {"summary": {"healthy": True}}
    assert len(restored.curiosity_queue) == 1
    assert len(restored.curiosity_inflight) == 1


def test_continuity_snapshot_detects_mutation(tmp_path):
    path = tmp_path / "session.json"
    manager = ContinuityStateManager(path)
    manager.save(ContinuitySnapshot(mood="calm"))
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["snapshot"]["mood"] = "tampered"
    path.write_text(json.dumps(stored), encoding="utf-8")

    with pytest.raises(SnapshotDivergenceError, match="digest mismatch"):
        manager.load()


def test_continuity_snapshot_noise_does_not_change_digest():
    base_payload = {
        "mood": "steady",
        "readiness": {"summary": {"ok": True}},
        "curiosity_queue": [],
        "curiosity_inflight": [],
        "last_readiness_ts": None,
    }
    canonical = canonicalise_continuity_snapshot(base_payload)
    digest = continuity_snapshot_digest(canonical)

    noisy_payload = {
        **base_payload,
        "transient": {"cache": True, "debug": [1, 2, 3]},
        "readiness": {"summary": {"ok": True}, "non_authoritative": "ignored"},
    }
    noisy_canonical = canonicalise_continuity_snapshot(noisy_payload)
    noisy_digest = continuity_snapshot_digest(noisy_canonical)

    assert canonical == noisy_canonical
    assert digest == noisy_digest


def test_gradient_fields_rejected_before_digest(tmp_path):
    path = tmp_path / "session.json"
    payload = {
        "curiosity_queue": [{"goal": {"id": "g-3"}, "delta": 1.0}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager = ContinuityStateManager(path)

    with pytest.raises(GradientInvariantViolation):
        manager.load()
