from datetime import datetime, timedelta, timezone

import pytest

from codex import (
    ExpressionBridge,
    FeedbackIngressForbidden,
    IntentDraftLedger,
    PublishWindowClosedError,
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


def _mature_draft(clock: FakeClock):
    ledger = IntentDraftLedger(
        expire_after=timedelta(minutes=15),
        decay_after=timedelta(minutes=5),
        evaluator=None,
        now=clock.now,
    )
    draft = ledger.append(
        label="stable reflection",
        trigger="audit",
        confidence=0.8,
        volatility=0.05,
    )
    clock.advance(2)
    ledger.reaffirm(draft.draft_id)
    draft.readiness = ReadinessBand.MATURE
    draft.non_executable = False
    return draft


def test_expression_requires_open_window() -> None:
    clock = FakeClock()
    bridge = ExpressionBridge(now=clock.now)
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="One-way status broadcast",
        epistemic_basis="operator approved",
        confidence_band="stable",
    )

    with pytest.raises(PublishWindowClosedError):
        bridge.emit(artifact, platform="log")


def test_window_closes_after_single_emission() -> None:
    clock = FakeClock()
    bridge = ExpressionBridge(now=clock.now)
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="Heartbeat emitted",
        epistemic_basis="manual review",
        confidence_band="stable",
    )

    window = bridge.open_window(opened_by="human reviewer", ttl=timedelta(seconds=5))
    assert window.is_open() is True
    bridge.emit(artifact, platform="status bus")

    assert bridge._window is None or bridge._window.is_open() is False
    with pytest.raises(PublishWindowClosedError):
        bridge.emit(artifact, platform="status bus")


def test_no_feedback_ingress_and_state_is_inert() -> None:
    clock = FakeClock()
    bridge = ExpressionBridge(now=clock.now)
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="Curated status",
        epistemic_basis="manual review",
        confidence_band="stable",
    )

    before_state = bridge.state_snapshot()
    bridge.open_window(opened_by="operator", ttl=timedelta(seconds=3))
    bridge.emit(artifact, platform="status logger")
    after_state = bridge.state_snapshot()

    assert before_state == after_state

    with pytest.raises(FeedbackIngressForbidden):
        bridge.ingestion_forbidden({"reaction": "like"})


def test_autopsy_is_generated_without_side_effects() -> None:
    clock = FakeClock()
    bridge = ExpressionBridge(now=clock.now)
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="Reflection capsule",
        epistemic_basis="manual review",
        confidence_band="stable",
    )

    bridge.open_window(opened_by="operator", ttl=timedelta(seconds=4))
    bridge.emit(artifact, platform="sealed channel")

    autopsies = bridge.autopsies()
    assert len(autopsies) == 1
    autopsy = autopsies[0]
    assert autopsy["emitted"] is True
    assert autopsy["state_influence"] == {"curiosity": False, "synthesis": False, "belief": False}
    assert autopsy["silence_preferred"] is False
