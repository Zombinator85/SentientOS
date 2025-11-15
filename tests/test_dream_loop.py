from datetime import datetime, timezone
from datetime import datetime, timezone
from types import SimpleNamespace

from sentientos.memory.dream_loop import DreamLoop
from sentientos.memory.glow import count_glow_shards, load_recent_glow_cache
from sentientos.memory.mounts import ensure_memory_mounts
from sentientos.memory.pulse_view import PulseEvent


def _pulse(kind: str, minute: int) -> PulseEvent:
    ts = datetime(2024, 3, 10, 12, minute, tzinfo=timezone.utc)
    return PulseEvent(ts=ts, kind=kind, severity="info", source=f"source.{kind}", payload={})


def test_dream_loop_run_once_writes_shard(monkeypatch, tmp_path):
    mounts = ensure_memory_mounts(tmp_path / "SentientOS")
    pulses = [_pulse("experiment", 1), _pulse("experiment", 2)]
    call_count = {"count": 0}

    def fake_collect(runtime, since):
        call_count["count"] += 1
        return list(pulses) if call_count["count"] == 1 else []

    messages = []

    def log_cb(message, extra=None):
        messages.append((message, extra))

    monkeypatch.setattr("sentientos.memory.dream_loop.collect_recent_pulse", fake_collect)

    runtime = SimpleNamespace()
    loop = DreamLoop(runtime, mounts, interval_seconds=10, log_cb=log_cb, max_recent_shards=3)

    assert loop.run_once() is True
    status = loop.status()
    assert status["last_focus"] == "experiments"
    assert count_glow_shards(mounts) == 1
    cache = load_recent_glow_cache(mounts)
    assert cache[-1]["focus"] == "experiments"
    assert any(message.startswith("DreamLoop: wrote shard") for message, _ in messages)

    assert loop.run_once() is False


def test_dream_loop_handles_empty_pulses(monkeypatch, tmp_path):
    mounts = ensure_memory_mounts(tmp_path / "SentientOS")
    monkeypatch.setattr("sentientos.memory.dream_loop.collect_recent_pulse", lambda runtime, since: [])
    runtime = SimpleNamespace()
    loop = DreamLoop(runtime, mounts, interval_seconds=10, log_cb=lambda *_: None)
    assert loop.run_once() is False
    assert count_glow_shards(mounts) == 0
