from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from sentientos.curiosity_scheduler import CuriosityLimiter, CuriosityScheduler, ExternalWitnessGate
from sentientos.daemons.chronos_daemon import ChronosDaemon


pytestmark = pytest.mark.no_legacy_skip


def test_chronos_day_rollover(tmp_path):
    timestamps = iter(
        [
            datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 23, 50, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 0, 5, tzinfo=timezone.utc),
        ]
    )
    chronos = ChronosDaemon(state_path=tmp_path / "temporal_state.json", now_fn=lambda: next(timestamps))

    first = chronos.tick()
    assert first["new_day"] is False

    second = chronos.tick()
    assert second["new_day"] is False

    rollover = chronos.tick(summary_pointer="/logs/daily_digest.jsonl")
    assert rollover["new_day"] is True
    assert rollover["event"]["type"] == "new_day"
    assert rollover["event"]["day_hash"]
    assert rollover["event"]["summary_pointer"] == "/logs/daily_digest.jsonl"

    persisted = json.loads((tmp_path / "temporal_state.json").read_text())
    assert set(persisted) == {"date", "last_seen", "session_id"}
    assert persisted["date"] == "2024-01-02"


def test_curiosity_scheduler_runs_only_when_idle():
    limiter = CuriosityLimiter(daily_cap=5, emotional_cooldown_seconds=10)
    scheduler = CuriosityScheduler(limiter=limiter)
    tasks = [
        {"source": "news", "summary": "observed topic", "confidence": 0.7},
        {"source": "docs", "summary": "read spec", "confidence": 0.8},
    ]

    assert scheduler.run_idle_cycle(tasks, idle=False) == []

    fragments = scheduler.run_idle_cycle(tasks, idle=True)
    assert len(fragments) == 2
    assert all(fragment["payload"].get("summary") for fragment in fragments)
    assert all("action" not in fragment["payload"] for fragment in fragments)
    assert scheduler.log


def test_external_witness_gate_read_only():
    gate = ExternalWitnessGate()
    record = gate.ingest(source="web", content={"title": "example"})
    assert record["non_canonical"] is True
    assert record["authoritative"] is False
    assert gate.audit_log and gate.audit_log[0]["mode"] == "read"

    with pytest.raises(PermissionError):
        gate.ingest(source="social", content={"thread": 1}, mode="write")

    approved = gate.ingest(
        source="social",
        content={"thread": 2},
        mode="write",
        intent={"type": "ExpressionIntent", "approved": True},
    )
    assert approved["mode"] == "write"


def test_curiosity_limiter_emits_advisories():
    now_points = iter([0.0, 10.0, 20.0, 70.0, 140.0])
    limiter = CuriosityLimiter(
        daily_cap=2,
        emotional_cooldown_seconds=50,
        saturation_threshold=0.5,
        now_fn=lambda: next(now_points),
    )

    allowed, advisories = limiter.assess({"emotional_density": 0.7, "source": "feed"})
    assert allowed is True
    assert "cooldown_started" in advisories

    allowed_after, advisories_after = limiter.assess({"source": "feed"})
    assert allowed_after is False
    assert "cooldown_active" in advisories_after

    allowed_final, advisories_final = limiter.assess({"source": "feed"})
    assert allowed_final is False
    assert "cooldown_active" in advisories_final

    allowed_post_cooldown, advisories_post_cooldown = limiter.assess({"source": "feed"})
    assert allowed_post_cooldown is True
    assert "approaching_saturation" in advisories_post_cooldown
    allowed_cap, advisories_cap = limiter.assess({"source": "feed"})
    assert allowed_cap is False
    assert "daily_cap_reached" in advisories_cap
