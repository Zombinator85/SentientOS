from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import pytest

from sentientos.developmental_model_replacement_experiment import (
    CONDITION_ORDER, PURPOSE, CognitiveModelIdentity, DevelopmentalModelReplacementError,
    DevelopmentalModelReplacementExperiment, FrozenCausalContext,
    ModelDevelopmentClaim, ModelDevelopmentProvenance,
)
from sentientos.local_model_authority import digest_payload

pytestmark = pytest.mark.no_legacy_skip


def digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def identity(name: str) -> CognitiveModelIdentity:
    active = {"model_id": name, "artifact": f"artifact-{name}", "configuration": f"cfg-{name}"}
    return CognitiveModelIdentity.create(
        model_id=name, semantic_artifact_identity=f"artifact-{name}",
        model_content_sha256=digest({"model": name}), artifact_size_bytes=10,
        sidecar_metadata_digest=digest({"sidecar": name}),
        configuration_digest=digest({"configuration": name}),
        engine_runtime_family="deterministic-test-runtime", candidate_index=0,
        active_production=True, fallback=False, authority_record_id=f"authority-{name}",
        authority_record_digest=digest({"authority": name}), active_model_identity=active,
        active_model_identity_digest=digest(active))


def context() -> FrozenCausalContext:
    current = {"facts": [{"fact_id": "fact-1", "payload": {"value": 1}}],
               "sources": [{"source_id": "source-1"}], "conflicts": []}
    history = ({"record_id": "record-1", "record_digest": digest({"record": 1}),
                "interpretation": "bounded prior"},)
    instruction = "Observe current evidence with optional history; history is not truth or authority."
    return FrozenCausalContext.create(
        snapshot_id="snapshot-1", snapshot_digest=digest({"snapshot": 1}),
        current_projection_id="projection-1", current_projection_digest=digest({"projection": current}),
        current_fact_ids=("fact-1",), projected_content_digest=digest(current),
        current_projection_payload=current, history_record_ids=("record-1",),
        history_record_digests=(history[0]["record_digest"],),
        history_record_set_digest=digest({"record_ids": ["record-1"],
                                          "record_digests": [history[0]["record_digest"]]}),
        history_projection_payload=history, instruction_template=instruction,
        instruction_template_digest=digest({"instruction": instruction}),
        inference_budget={"max_input_chars": 16000, "max_output_chars": 4000,
                          "max_new_tokens": 512, "timeout_seconds": 30,
                          "max_calls_per_correlation": 1},
        generation_posture={"temperature": 0, "hardware_determinism_claimed": False},
        repository_generation_identity="test-sha")


class FakeEndpoint:
    def __init__(self, model: CognitiveModelIdentity, *, history_effect: bool = True) -> None:
        self.identity = model
        self.history_effect = history_effect
        self.calls: list[dict[str, Any]] = []
        self.drift_after: int | None = None

    def current_identity(self) -> CognitiveModelIdentity:
        if self.drift_after is not None and len(self.calls) >= self.drift_after:
            return identity(self.identity.model_id + "-drift")
        return self.identity

    def infer(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        prompt = json.loads(kwargs["prompt"])
        history = bool(prompt["developmental_history"])
        semantic = {"model": self.identity.model_id,
                    "history": history if self.history_effect else "ignored"}
        number = len(self.calls)
        return {"status": "admitted_completed", "fallback_occurred": False,
                "request_id": f"request-{self.identity.model_id}-{number}",
                "request_digest": digest({"request": self.identity.model_id, "number": number}),
                "inference_receipt_id": f"receipt-{self.identity.model_id}-{number}",
                "inference_receipt_digest": digest({"receipt": self.identity.model_id, "number": number}),
                "output_digest": digest(semantic),
                "actual_generation_parameters": {"temperature": 0, "max_new_tokens": 512}}


def experiment(tmp_path: Path, *, a_effect: bool = True, b_effect: bool = True,
               provenance_a: ModelDevelopmentProvenance | None = None,
               provenance_b: ModelDevelopmentProvenance | None = None):
    a, b = FakeEndpoint(identity("a"), history_effect=a_effect), FakeEndpoint(identity("b"), history_effect=b_effect)
    exp = DevelopmentalModelReplacementExperiment(context=context(), model_a=a, model_b=b,
        artifact_root=tmp_path, model_a_provenance=provenance_a,
        model_b_provenance=provenance_b)
    return exp, a, b


def test_preregistered_five_condition_model_replacement_experiment(tmp_path: Path) -> None:
    exp, a, b = experiment(tmp_path)
    result = exp.run()
    assert [o["condition_id"] for o in result["observations"]] == list(CONDITION_ORDER)
    assert len(a.calls) == 3 and len(b.calls) == 2
    protocol_path = exp.store.protocols / f"{exp.protocol.protocol_id}.json"
    assert protocol_path.exists() and protocol_path.stat().st_mtime_ns <= exp.store.runs.joinpath(result["run_id"] + ".json").stat().st_mtime_ns
    assert result["validity"] == "valid_controlled_observation"


def test_exact_shared_current_and_history_state_across_models(tmp_path: Path) -> None:
    exp, a, b = experiment(tmp_path)
    history_before = json.dumps(exp.context.history_projection_payload, sort_keys=True)
    result = exp.run()
    calls = a.calls[:2] + b.calls
    current_payloads = [json.loads(call["prompt"])["current_evidence"] for call in calls]
    assert all(value == current_payloads[0] for value in current_payloads)
    assert a.calls[0]["prompt"] == b.calls[0]["prompt"]
    assert a.calls[1]["prompt"] == b.calls[1]["prompt"]
    assert a.calls[0]["upstream_evidence"]["record_ids"] == b.calls[0]["upstream_evidence"]["record_ids"]
    assert a.calls[1]["upstream_evidence"]["record_ids"] == b.calls[1]["upstream_evidence"]["record_ids"] == []
    assert json.dumps(exp.context.history_projection_payload, sort_keys=True) == history_before
    assert all(o["current_projection_digest"] == exp.context.current_projection_digest for o in result["observations"])
    assert "model_a" not in a.calls[0]["prompt"] and "teacher" not in a.calls[0]["prompt"]


def test_history_association_measured_independently_under_both_models(tmp_path: Path) -> None:
    result = experiment(tmp_path)[0].run()
    assert result["differences"] == {
        "history_effect_model_a": True, "history_effect_model_b": True,
        "model_difference_with_history": True, "model_difference_without_history": True,
        "model_a_restoration": True}
    assert result["classification"] == "history_association_observed_under_both_cognitive_models"
    forbidden = {"learning", "selfhood", "identity_persistence", "consciousness", "sentience", "causal_closure"}
    assert not forbidden.intersection(result)


@pytest.mark.parametrize(("a_effect", "b_effect", "classification"), [
    (True, False, "history_association_observed_model_a_only"),
    (False, True, "history_association_observed_model_b_only"),
    (False, False, "no_observable_history_effect_either_model"),
])
def test_bounded_history_classifications(tmp_path: Path, a_effect: bool, b_effect: bool, classification: str) -> None:
    assert experiment(tmp_path, a_effect=a_effect, b_effect=b_effect)[0].run()["classification"] == classification


def test_exact_model_a_restoration(tmp_path: Path) -> None:
    exp, a, _ = experiment(tmp_path)
    result = exp.run()
    assert result["differences"]["model_a_restoration"]
    assert result["observations"][0]["model_identity_digest"] == result["observations"][4]["model_identity_digest"]
    assert a.calls[0]["prompt"] == a.calls[2]["prompt"]


def test_provenance_claim_remains_source_bound_non_truth_metadata(tmp_path: Path) -> None:
    subject = identity("a")
    claim = ModelDevelopmentClaim.create(subject_identity_digest=subject.identity_digest,
        relation_type="reported_teacher_student", claimed_parent_or_teacher="external-label",
        evidence_kind="operator_supplied_manifest", source_reference="manifest:1",
        evidence_digest=digest({"manifest": 1}), epistemic_posture="source_bound_reported_claim")
    provenance = ModelDevelopmentProvenance.create(subject, (claim,))
    a, b = FakeEndpoint(subject), FakeEndpoint(identity("b"))
    exp = DevelopmentalModelReplacementExperiment(context=context(), model_a=a, model_b=b,
        artifact_root=tmp_path, model_a_provenance=provenance)
    result = exp.run()
    assert provenance.grants_authority is False
    assert provenance.claims[0].epistemic_posture == "source_bound_reported_claim"
    assert provenance.claims[0].relation_type == "reported_teacher_student"
    assert "external-label" not in a.calls[0]["prompt"]
    assert result["protocol"]["model_a_identity"]["identity_digest"] == subject.identity_digest


def test_absent_provenance_is_unknown_not_inferred_from_name(tmp_path: Path) -> None:
    exp, _, _ = experiment(tmp_path)
    assert exp.provenance_a.availability == "unknown" and exp.provenance_a.claims == ()
    assert exp.provenance_b.availability == "unknown" and exp.provenance_b.claims == ()


def test_same_model_supplied_as_a_and_b_is_rejected(tmp_path: Path) -> None:
    same = identity("same")
    with pytest.raises(DevelopmentalModelReplacementError, match="not_distinct"):
        DevelopmentalModelReplacementExperiment(context=context(), model_a=FakeEndpoint(same),
            model_b=FakeEndpoint(same), artifact_root=tmp_path)


def test_crossed_or_tampered_provenance_is_rejected(tmp_path: Path) -> None:
    a, b = identity("a"), identity("b")
    crossed = ModelDevelopmentProvenance.create(b)
    with pytest.raises(DevelopmentalModelReplacementError, match="subject_mismatch"):
        DevelopmentalModelReplacementExperiment(context=context(), model_a=FakeEndpoint(a),
            model_b=FakeEndpoint(b), artifact_root=tmp_path, model_a_provenance=crossed)
    tampered = replace(ModelDevelopmentProvenance.create(a), availability="reported")
    with pytest.raises(DevelopmentalModelReplacementError, match="digest_mismatch"):
        DevelopmentalModelReplacementExperiment(context=context(), model_a=FakeEndpoint(a),
            model_b=FakeEndpoint(b), artifact_root=tmp_path, model_a_provenance=tampered)


def test_model_identity_drift_and_a_restoration_mismatch_fail_closed(tmp_path: Path) -> None:
    exp, a, _ = experiment(tmp_path); a.drift_after = 1
    with pytest.raises(DevelopmentalModelReplacementError, match="model_identity_drift"):
        exp.run()
    exp2, a2, _ = experiment(tmp_path / "second"); a2.drift_after = 2
    with pytest.raises(DevelopmentalModelReplacementError, match="model_identity_drift"):
        exp2.run()


def test_nonproduction_fallback_and_identity_tampering_are_rejected(tmp_path: Path) -> None:
    valid = identity("a")
    for invalid in (replace(valid, active_production=False), replace(valid, fallback=True),
                    replace(valid, configuration_digest="sha256:changed")):
        with pytest.raises(DevelopmentalModelReplacementError):
            DevelopmentalModelReplacementExperiment(context=context(), model_a=FakeEndpoint(invalid),
                model_b=FakeEndpoint(identity("b")), artifact_root=tmp_path)


def test_protocol_provenance_and_run_custody_detect_tampering(tmp_path: Path) -> None:
    exp, _, _ = experiment(tmp_path); result = exp.run()
    protocol = exp.store.protocols / f"{exp.protocol.protocol_id}.json"
    protocol.write_text("{}", encoding="utf-8")
    with pytest.raises(DevelopmentalModelReplacementError, match="artifact_identity_collision"):
        exp.run()
    run_path = exp.store.runs / f"{result['run_id']}.json"
    run_path.write_text("{}", encoding="utf-8")
    with pytest.raises(DevelopmentalModelReplacementError, match="artifact_identity_collision"):
        exp.store.persist_run({k: v for k, v in result.items() if k not in {"run_id", "run_digest"}})


def test_developmental_history_mutation_attempt_is_detected_before_inference(tmp_path: Path) -> None:
    exp, _, _ = experiment(tmp_path)
    exp.context = replace(exp.context, history_projection_payload=({"changed": True},))
    with pytest.raises(DevelopmentalModelReplacementError, match="causal_context_digest_mismatch"):
        exp.run()


def test_generation_posture_and_purpose_are_fixed(tmp_path: Path) -> None:
    exp, a, b = experiment(tmp_path); exp.run()
    for call in a.calls + b.calls:
        assert call["purpose"] == PURPOSE
        assert call["generation_posture"] == {"temperature": 0, "hardware_determinism_claimed": False}
        assert call["budget"]["max_new_tokens"] == 512
