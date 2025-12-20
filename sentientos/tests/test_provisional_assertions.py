from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
import json

import pytest

from sentientos.truth import (
    AntiLagGuard,
    ConfidenceDecayEngine,
    NarrativeSynopsisGenerator,
    ProvisionalAssertionLedger,
    SilenceDebt,
)


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


def test_inquiry_generation_links_to_backlog_and_review():
    ledger = ProvisionalAssertionLedger()
    now = datetime.utcnow()
    active = ledger.create_assertion(
        claim_text="drift-detection",
        confidence_band="MEDIUM",
        evidence_summary="telemetry divergence",
        review_horizon=now + timedelta(minutes=5),
    )
    retracted = ledger.retract(
        active.assertion_id,
        cause="not reproducible",
        review_horizon=now + timedelta(minutes=10),
    )
    backlog: dict[str, list[dict[str, object]]] = {}
    ledger.enqueue_inquiry_prompts(backlog, resolved_ids={retracted.assertion_id})
    prompts = backlog["inquiry_prompts"]
    assert {prompt["related_assertion_id"] for prompt in prompts} == {active.assertion_id}
    assert prompts[0]["direction"] == "discriminate"
    assert prompts[0]["priority_hint"] > 0
    assert "review_horizon" not in prompts[0]


def test_decay_triggers_and_is_reversible():
    ledger = ProvisionalAssertionLedger()
    horizon = datetime.utcnow() - timedelta(minutes=1)
    assertion = ledger.create_assertion(
        claim_text="latency-regression",
        confidence_band="HIGH",
        evidence_summary="packet loss spike",
        review_horizon=horizon,
    )
    engine = ConfidenceDecayEngine(default_extension=timedelta(minutes=30))
    log = engine.apply_decay(ledger, now=datetime.utcnow())
    assert log[0]["from_band"] == "HIGH"
    chain = ledger.supersession_chain(assertion.assertion_id)
    assert chain[-1].confidence_band == "MEDIUM"

    restored = ledger.revise_confidence(
        chain[-1].assertion_id,
        new_band="HIGH",
        evidence_summary="reviewed and reaffirmed",
        review_horizon=datetime.utcnow() + timedelta(hours=1),
    )
    assert restored.confidence_band == "HIGH"


def test_pinned_assertions_resist_decay():
    ledger = ProvisionalAssertionLedger()
    assertion = ledger.create_assertion(
        claim_text="stability",
        confidence_band="HIGH",
        evidence_summary="long-run monitoring",
        review_horizon=datetime.utcnow() - timedelta(minutes=5),
        decay_pinned=True,
    )
    engine = ConfidenceDecayEngine()
    log = engine.apply_decay(ledger, now=datetime.utcnow())
    assert log == []
    assert ledger.supersession_chain(assertion.assertion_id)[-1].confidence_band == "HIGH"


def test_narrative_is_deterministic_and_includes_history():
    ledger = ProvisionalAssertionLedger()
    base = ledger.create_assertion(
        claim_text="coverage-gap",
        confidence_band="MEDIUM",
        evidence_summary="missing tests",
        review_horizon=datetime.utcnow() + timedelta(minutes=30),
    )
    superseded = ledger.revise_confidence(
        base.assertion_id,
        new_band="LOW",
        evidence_summary="tests added",
        review_horizon=datetime.utcnow() + timedelta(hours=1),
    )
    generator = NarrativeSynopsisGenerator()
    chain = ledger.supersession_chain(base.assertion_id)
    first = generator.build(chain)
    second = generator.build(chain)
    assert first.synopsis_text == second.synopsis_text
    assert base.assertion_id in first.synopsis_text or superseded.assertion_id in first.synopsis_text
    claim_texts = {entry["claim_text"] for entry in first.outline["claims"]}
    assert claim_texts == {"coverage-gap"}
