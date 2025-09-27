from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import json
import pytest

from codex import (
    Anomaly,
    AnomalyDetector,
    AnomalyEmitter,
    EmbodimentMount,
    IntentPrioritizer,
    PriorityScoringEngine,
)


@dataclass
class ManualClock:
    moment: datetime

    def now(self) -> datetime:
        return self.moment

    def tick(self, delta: timedelta) -> None:
        self.moment += delta


def _embodiment_anomalies(tmp_path: Path, clock: ManualClock, *, critical_noise: bool = True) -> List[Anomaly]:
    mount = EmbodimentMount(tmp_path / "embodiment", now=clock.now)
    motion = mount.ingest(
        "camera_feed",
        {"unexpected": True, "period": "night", "confidence": 0.9, "magnitude": 1.2},
        event_type="motion",
    )
    noise_primary = mount.ingest(
        "audio_events",
        {"decibel": 87, "threshold": 60, "confidence": 0.65},
        event_type="noise",
    )
    noise_events = [noise_primary]
    if critical_noise:
        noise_events.append(
            mount.ingest(
                "audio_events",
                {"decibel": 92, "threshold": 60, "confidence": 0.7, "profanity": True},
                event_type="noise",
            )
        )
    absence = mount.ingest(
        "camera_feed",
        {"status": "offline", "expected": True, "confidence": 0.55},
        event_type="status",
    )

    detector = AnomalyDetector(now=clock.now)
    events = [event.to_record() for event in (motion, *noise_events, absence)]
    return detector.analyze([], [], [], embodiment_events=events)


def test_embodiment_streams_emit_anomalies(tmp_path: Path) -> None:
    clock = ManualClock(moment=datetime(2025, 3, 1, 3, 14, tzinfo=timezone.utc))
    anomalies = _embodiment_anomalies(tmp_path, clock)

    kinds = {anomaly.kind for anomaly in anomalies}
    assert {"embodiment_motion", "embodiment_noise", "embodiment_absence"} <= kinds

    emitter = AnomalyEmitter(tmp_path / "pulse" / "anomalies")
    for anomaly in anomalies:
        emitter.emit(anomaly)

    log_path = tmp_path / "pulse" / "anomalies" / f"{clock.now().date().isoformat()}.jsonl"
    payloads = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(payloads) == len(anomalies)
    for entry in payloads:
        assert "embodiment" in entry.get("tags", [])
        assert entry.get("impact") == "environment"
        assert entry.get("source") in {"camera_feed", "audio_events"}


def test_prioritizer_ranks_embodiment_against_daemon(tmp_path: Path) -> None:
    clock = ManualClock(moment=datetime(2025, 3, 1, 3, 14, tzinfo=timezone.utc))
    embodiment_anomalies = _embodiment_anomalies(tmp_path, clock, critical_noise=False)

    daemon_anomaly = Anomaly(
        "daemon_cooldown_breach",
        "Daemon cooldown breach detected",
        "high",
        {"daemon": "CoolingDaemon", "impact": "daemon", "confidence": 0.6},
        timestamp=clock.now(),
    )

    prioritizer = IntentPrioritizer(PriorityScoringEngine(), now=clock.now)
    intent = prioritizer.evaluate(anomalies=[daemon_anomaly, *embodiment_anomalies])

    assert intent is not None
    assert intent.item_type == "anomaly"

    candidates = {candidate.candidate_id: candidate for candidate in prioritizer.candidates}
    absence_key = next(key for key in candidates if key.startswith("anomaly:embodiment_absence"))
    daemon_key = "anomaly:daemon_cooldown_breach:CoolingDaemon"

    assert absence_key in candidates
    assert daemon_key in candidates
    absence_candidate = candidates[absence_key]
    daemon_candidate = candidates[daemon_key]

    assert absence_candidate.score >= daemon_candidate.score
    assert intent.candidate_id != daemon_key
    assert "embodiment" in absence_candidate.payload["metadata"].get("tags", [])


def test_operator_controls_toggle_lock_and_quarantine(tmp_path: Path) -> None:
    mount = EmbodimentMount(tmp_path / "embodiment")

    assert mount.is_enabled("audio_events")
    mount.toggle("audio_events", False)
    assert not mount.is_enabled("audio_events")
    with pytest.raises(PermissionError):
        mount.ingest("audio_events", {"decibel": 40}, event_type="noise")

    mount.toggle("audio_events", True)
    mount.lock("audio_events")
    assert not mount.is_enabled("audio_events")
    with pytest.raises(PermissionError):
        mount.ingest("audio_events", {"decibel": 41}, event_type="noise")

    mount.unlock("audio_events")
    event = mount.ingest("audio_events", {"decibel": 42}, event_type="noise")
    quarantine_path = mount.quarantine(event.to_record(), reason="review")
    assert quarantine_path.exists()
    assert mount.quarantined_events
    assert mount.quarantined_events[-1]["reason"] == "review"
    assert "embodiment" in mount.quarantined_events[-1].get("tags", [])
