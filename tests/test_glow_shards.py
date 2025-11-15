from datetime import datetime, timezone
from pathlib import Path

from sentientos.memory.glow import (
    build_glow_shard,
    count_glow_shards,
    load_recent_glow_cache,
    render_reflection_line,
    save_glow_shard,
)
from sentientos.memory.mounts import ensure_memory_mounts
from sentientos.memory.pulse_view import PulseEvent


def _pulse(ts_offset: int, kind: str, severity: str, source: str, payload: dict[str, object]) -> PulseEvent:
    ts = datetime(2024, 3, 10, 12, ts_offset, tzinfo=timezone.utc)
    return PulseEvent(ts=ts, kind=kind, severity=severity, source=source, payload=payload)


def test_build_glow_shard_governance_focus() -> None:
    pulses = [
        _pulse(1, "cathedral", "warn", "cathedral.review", {"status": "quarantined"}),
        _pulse(2, "rollback", "info", "cathedral.rollback", {"amendment_id": "amend-1"}),
    ]
    shard = build_glow_shard(pulses)
    assert shard.focus == "governance"
    assert shard.summary == "I examined several governance changes and kept my configuration safe."
    assert sorted(shard.tags) == ["cathedral", "rollback", "safety"]
    assert len(shard.pulses) == 2


def test_build_glow_shard_experiment_focus() -> None:
    pulses = [
        _pulse(1, "experiment", "info", "experiments.chain", {"success": True}),
        _pulse(2, "experiment", "error", "experiments.chain", {"success": False}),
    ]
    shard = build_glow_shard(pulses)
    assert shard.focus == "experiments"
    assert shard.summary.startswith("I ran experiments")
    assert "experiments" in shard.tags


def test_save_glow_shard_updates_journal_and_cache(tmp_path: Path) -> None:
    mounts = ensure_memory_mounts(tmp_path / "SentientOS")
    pulses = [
        _pulse(1, "federation", "warn", "federation.peer", {"level": "drift"}),
        _pulse(2, "persona", "info", "persona.loop", {"reflection": "steady"}),
    ]
    shard = build_glow_shard(pulses)
    journal_path = save_glow_shard(mounts, shard, max_recent=2)
    assert journal_path.exists()
    assert count_glow_shards(mounts) == 1

    cache = load_recent_glow_cache(mounts)
    assert len(cache) == 1
    assert cache[0]["id"] == shard.id
    assert cache[0]["focus"] == shard.focus

    reflection_line = render_reflection_line(cache[0])
    assert isinstance(reflection_line, str)
    assert reflection_line
