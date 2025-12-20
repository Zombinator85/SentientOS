from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
import json

import pytest

from sentientos.truth import AntiLagGuard, ProvisionalAssertionLedger, SilenceDebt


def test_records_low_confidence_assertion_with_review_clock():
    ledger = ProvisionalAssertionLedger()
    horizon = datetime.utcnow() + timedelta(hours=1)

    assertion = ledger.create_assertion(
        claim_text="emerging-pattern",
        confidence_band="LOW",
        evidence_summary="mechanism sketch before consensus",
        review_horizon=horizon,
    )

    due = ledger.due_for_review(now=horizon + timedelta(minutes=1))
    assert assertion in ledger.supersession_chain(assertion.assertion_id)
    assert any(item.assertion_id == assertion.assertion_id for item in due)


def test_confidence_revision_produces_supersession_chain():
    ledger = ProvisionalAssertionLedger()
    base = ledger.create_assertion(
        claim_text="signal drift",
        confidence_band="LOW",
        evidence_summary="first sighting",
        review_horizon=datetime.utcnow() + timedelta(hours=2),
    )

    revised = ledger.revise_confidence(
        base.assertion_id,
        new_band="MEDIUM",
        evidence_summary="pattern reinforced",
        review_horizon=datetime.utcnow() + timedelta(hours=4),
    )

    chain = ledger.supersession_chain(base.assertion_id)
    assert chain[0].assertion_id == base.assertion_id
    assert chain[0].superseded_by == (revised.assertion_id,)
    assert chain[-1].assertion_id == revised.assertion_id


def test_supersession_chain_handles_retraction_without_editing_old_entries():
    ledger = ProvisionalAssertionLedger()
    first = ledger.create_assertion(
        claim_text="interference",
        confidence_band="MEDIUM",
        evidence_summary="sensor cross-talk",
        review_horizon=datetime.utcnow() + timedelta(hours=1),
    )
    second = ledger.revise_confidence(
        first.assertion_id,
        new_band="HIGH",
        evidence_summary="validated in duplicate sensor",
        review_horizon=datetime.utcnow() + timedelta(hours=3),
    )
    retraction = ledger.retract(
        second.assertion_id,
        cause="false positive confirmed",
        review_horizon=datetime.utcnow() + timedelta(hours=6),
    )

    chain = ledger.supersession_chain(first.assertion_id)
    assert chain[0].assertion_id == first.assertion_id
    assert chain[1].assertion_id == second.assertion_id
    assert chain[2].assertion_id == retraction.assertion_id
    with pytest.raises(FrozenInstanceError):
        # Immutable once written
        retraction.claim_text = "edited"


def test_anti_lag_guard_refuses_silence_under_pressure():
    guard = AntiLagGuard(signal_threshold=0.8)
    ledger = ProvisionalAssertionLedger()

    with pytest.raises(SilenceDebt):
        guard.detect_silence(signals=[0.2, 1.2], topic="overload", assertions=[])

    seeded = ledger.create_assertion(
        claim_text="overload",
        confidence_band="LOW",
        evidence_summary="pressure telemetry spike",
        review_horizon=datetime.utcnow() + timedelta(minutes=45),
    )

    result = guard.detect_silence(signals=[0.2, 1.2], topic="overload", assertions=[seeded])
    assert result["status"] == "covered"


def test_deterministic_serialization_and_integrations():
    ledger = ProvisionalAssertionLedger()
    now = datetime.utcnow()
    first = ledger.create_assertion(
        claim_text="lag debt",
        confidence_band="LOW",
        evidence_summary="queue empty while signals rise",
        review_horizon=now + timedelta(minutes=15),
    )
    ledger.create_assertion(
        claim_text="lag debt",
        confidence_band="MEDIUM",
        evidence_summary="queue populated",
        review_horizon=now + timedelta(minutes=20),
        supersedes=first.assertion_id,
    )

    serialized = ledger.serialize()
    assert serialized == ledger.serialize()
    payload = json.loads(serialized)
    assert all(entry["schema_version"] == first.schema_version for entry in payload)

    queue: dict[str, list[dict[str, object]]] = {}
    ledger.enqueue_reviews(queue, now=now + timedelta(minutes=30))
    assert queue["provisional_assertions"]

    pressure_log: dict[str, object] = {}
    ledger.annotate_pressure_log(pressure_log, context="integration-test")
    assert pressure_log["epistemic_annotations"][0]["context"] == "integration-test"

    tooling_status: dict[str, object] = {}
    ledger.annotate_tooling_status(tooling_status)
    assert "active" in tooling_status.get("provisional_assertions", {})
