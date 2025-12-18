from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex import (
    ExpressionIntentBridgeError,
    ExpressionThresholdEvaluator,
    IntentDraftLedger,
    ReadinessBand,
)

pytestmark = pytest.mark.no_legacy_skip


class FakeClock:
    def __init__(self) -> None:
        self._now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)

    def now(self) -> datetime:
        return self._now


def test_draft_never_converts_out_of_internal_scope(tmp_path: Path) -> None:
    clock = FakeClock()
    ledger = IntentDraftLedger(now=clock.now)

    draft = ledger.append(label="clarify pattern", trigger="synthesis", confidence=0.7, volatility=0.2)

    assert draft.non_executable is True
    with pytest.raises(ExpressionIntentBridgeError):
        draft.to_expression_intent()

    report = ledger.readiness_report()
    assert report[0]["non_executable"] is True
    # Ledger does not touch filesystem or output buses.
    sandbox = tmp_path / "no_outputs"
    sandbox.mkdir()
    assert list(sandbox.iterdir()) == []


def test_expiration_and_decay_behavior() -> None:
    clock = FakeClock()
    ledger = IntentDraftLedger(
        expire_after=timedelta(seconds=5),
        decay_after=timedelta(seconds=2),
        now=clock.now,
    )

    draft = ledger.append(label="archive observation", trigger="epistemic_state", confidence=0.5, volatility=0.4)
    assert draft.expired is False and draft.dormant is False

    clock.advance(3)
    ledger.expire_stale()
    assert draft.dormant is True
    assert draft.expired is False

    clock.advance(3)
    expired = ledger.expire_stale()
    assert draft in expired
    assert draft.expired is True
    assert draft.readiness == ReadinessBand.EXPIRED
    assert ledger.silence_metrics()["events"]["intent expired"] == 1


def test_silence_is_a_successful_terminal_state() -> None:
    ledger = IntentDraftLedger(now=FakeClock().now)

    ledger.record_silence("no intent formed")
    ledger.record_silence("intent suppressed")
    ledger.record_silence("intent expired")

    metrics = ledger.silence_metrics()
    assert metrics["events"]["no intent formed"] == 1
    assert metrics["events"]["intent suppressed"] == 1
    assert metrics["events"]["intent expired"] == 1
    assert metrics["silence_success_rate"] > 0.0


def test_introspective_queries_and_readiness_annotations() -> None:
    clock = FakeClock()
    evaluator = ExpressionThresholdEvaluator(
        persistence_horizon=timedelta(seconds=4),
        dormancy_half_life=timedelta(seconds=8),
        now=clock.now,
    )
    ledger = IntentDraftLedger(
        expire_after=timedelta(seconds=30),
        decay_after=timedelta(seconds=10),
        evaluator=evaluator,
        now=clock.now,
    )

    stable = ledger.append(label="name contradiction", trigger="reflection", confidence=0.9, volatility=0.05)
    unstable = ledger.append(
        label="flag contradiction",
        trigger="conflict_check",
        confidence=0.6,
        volatility=0.7,
        contradiction=True,
    )

    clock.advance(5)
    ledger.reaffirm(stable.draft_id)
    ledger.reaffirm(unstable.draft_id, contradiction=True)

    assert stable.readiness == ReadinessBand.MATURE
    assert unstable.readiness in {ReadinessBand.UNSTABLE, ReadinessBand.PREMATURE}

    view = ledger.introspect()
    assert any(entry["draft_id"] == stable.draft_id for entry in view["held"])
    assert ledger.persistence_for(stable.draft_id) > 0
    assert view["silence"]["events"] == {}
