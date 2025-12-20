import pytest

from sentientos.integrity import (
    ExplanationContractViolation,
    ExplanationInputs,
    build_explanation_artifact,
    build_explanation_with_fallback,
    validate_explanation_artifact,
)


@pytest.fixture()
def example_inputs() -> ExplanationInputs:
    return ExplanationInputs(
        request={"id": "req-123", "fingerprint": "abc123"},
        provenance={"authority": "council", "scope": "test", "issued_at": "2025-08-30T12:00:00Z"},
        policy_decisions=[{"policy_id": "P-1", "decision": "allowed", "outcome": "Matched scope"}],
        execution_results=[{"action": "do-thing", "status": "succeeded", "result_reference": "result-1"}],
    )


def test_build_explanation_happy_path(example_inputs: ExplanationInputs) -> None:
    explanation = build_explanation_artifact(example_inputs)

    assert explanation["schema_version"] == "1.0"
    assert explanation["statements"][0]["text"] == "Request req-123 fingerprint abc123"
    assert "digest" in explanation and len(explanation["digest"]) == 64
    assert explanation["referenced_hashes"]["request"]


def test_replay_produces_identical_explanation(example_inputs: ExplanationInputs) -> None:
    first = build_explanation_artifact(example_inputs)
    second = build_explanation_artifact(example_inputs)

    assert first == second


def test_narrative_drift_rejected(example_inputs: ExplanationInputs) -> None:
    explanation = build_explanation_artifact(example_inputs)
    explanation["statements"] = list(explanation["statements"])
    explanation["statements"][0] = {
        "template": "request",
        "text": "system decided because it wanted to",
    }

    with pytest.raises(ExplanationContractViolation):
        validate_explanation_artifact(explanation, example_inputs)


def test_tamper_detection(example_inputs: ExplanationInputs) -> None:
    explanation = build_explanation_artifact(example_inputs)
    modified_inputs = ExplanationInputs(
        request=example_inputs.request,
        provenance=example_inputs.provenance,
        policy_decisions=[{"policy_id": "P-1", "decision": "denied", "outcome": "Tampered"}],
        execution_results=example_inputs.execution_results,
    )

    with pytest.raises(Exception):
        validate_explanation_artifact(explanation, modified_inputs)


def test_graceful_degradation_preserves_facts() -> None:
    inputs = ExplanationInputs(
        request={"id": "req-err", "fingerprint": "fp"},
        provenance={"authority": "council", "scope": "test", "issued_at": "2025-08-30T12:00:00Z"},
        policy_decisions=[{"policy_id": "P-2", "decision": "inferred", "outcome": "not allowed"}],
        execution_results=[{"action": "do-thing", "status": "succeeded", "result_reference": "result-1"}],
    )

    result = build_explanation_with_fallback(inputs)

    assert result["explanation"] is None
    assert result["facts"]["policy_decisions"][0]["decision"] == "inferred"
    assert "error" in result["facts"]
