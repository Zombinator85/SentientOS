from datetime import datetime, timezone

import pytest

from sentientos.curiosity_scheduler import (
    ContinuityLedger,
    NonEscalationEnforcer,
    PatternDormancyDetector,
    SynthesisDaemon,
)
from sentientos.daemons.chronos_daemon import ChronosDaemon


pytestmark = pytest.mark.no_legacy_skip


def test_cross_day_pattern_persistence(tmp_path):
    ledger = ContinuityLedger(path=tmp_path / "continuity.jsonl")
    ledger.record_observation(
        theme="alignment_signal",
        signal_strength=0.4,
        source="idle_cycle",
        timestamp="2024-01-01T02:00:00+00:00",
    )
    ledger.record_observation(
        theme="alignment_signal",
        signal_strength=0.6,
        source="idle_cycle",
        timestamp="2024-01-02T02:00:00+00:00",
    )

    assert ledger.is_ongoing("alignment_signal") is True
    assert ledger.signal_direction("alignment_signal") == "intensified"
    assert ledger.days_alive("alignment_signal", current_date="2024-01-02") == 1


def test_continuity_links_new_day_events(tmp_path):
    timestamps = iter(
        [
            datetime(2024, 1, 1, 22, 30, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 23, 50, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 0, 5, tzinfo=timezone.utc),
        ]
    )
    chronos = ChronosDaemon(state_path=tmp_path / "temporal.json", now_fn=lambda: next(timestamps))
    chronos.tick()
    rollover = chronos.tick(summary_pointer="/logs/daily_digest.jsonl")

    ledger = ContinuityLedger(path=tmp_path / "continuity.jsonl")
    ledger.record_observation(
        theme="alignment_signal",
        signal_strength=0.5,
        source="idle_cycle",
        timestamp="2024-01-01T23:00:00+00:00",
        day_hash=rollover["event"]["day_hash"],
    )
    link = ledger.link_new_day(rollover["event"], unresolved_patterns=("alignment_signal",))

    assert link["day_hash"] == rollover["event"]["day_hash"]
    assert "alignment_signal" in link["unresolved"]
    assert any(entry.get("type") == "day_link" for entry in ledger.history("alignment_signal"))


def test_dormancy_detected_after_decay(tmp_path):
    ledger = ContinuityLedger(path=tmp_path / "continuity.jsonl")
    ledger.record_observation(
        theme="ambient_noise",
        signal_strength=0.3,
        source="idle_cycle",
        timestamp="2024-01-01T02:00:00+00:00",
    )
    ledger.record_observation(
        theme="ambient_noise",
        signal_strength=0.18,
        source="idle_cycle",
        timestamp="2024-01-02T02:00:00+00:00",
    )
    ledger.record_observation(
        theme="ambient_noise",
        signal_strength=0.1,
        source="idle_cycle",
        timestamp="2024-01-03T02:00:00+00:00",
    )

    detector = PatternDormancyDetector(decay_threshold=0.2, stability_window=3)
    result = detector.evaluate(ledger, "ambient_noise")

    assert result == {"theme": "ambient_noise", "status": "dormant", "reason": "decayed"}
    assert ledger.is_ongoing("ambient_noise") is False


def test_synthesis_is_internal_only():
    fragments = [
        {
            "source": "observer",
            "confidence": 0.5,
            "payload": {"theme": "alignment_signal", "summary": "noted recurrence"},
        },
        {
            "source": "observer",
            "confidence": 0.55,
            "payload": {"theme": "alignment_signal", "summary": "intensity rising"},
        },
    ]
    daemon = SynthesisDaemon(enforcer=NonEscalationEnforcer(convergence_floor=0.2))
    notes = daemon.synthesize(fragments)

    assert notes
    assert all(note.get("expression_permitted") is False for note in notes)
    assert all(note.get("intent") is None for note in notes)
    assert any("advisory" in note for note in notes)

    enforcer = NonEscalationEnforcer()
    with pytest.raises(PermissionError):
        enforcer.ensure_internal_only({"intent": "publish", "summary": "should be blocked"})
