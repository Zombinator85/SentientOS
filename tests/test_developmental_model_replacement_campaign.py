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

from sentientos.developmental_model_replacement_campaign import (
    DevelopmentalModelReplacementCampaign, CampaignStore, MIN_TRIALS, MAX_TRIALS,
    PROTOCOL_SCHEMA, STATE_SCHEMA, REPORT_SCHEMA,
)


def campaign(tmp_path: Path, *, a_effect: bool = True, b_effect: bool = True, ids=("trial-1", "trial-2")):
    exp, a, b = experiment(tmp_path, a_effect=a_effect, b_effect=b_effect)
    return DevelopmentalModelReplacementCampaign.create(
        experiment=exp, artifact_root=tmp_path, trial_ids=ids), exp, a, b


def test_preregistered_multi_trial_campaign_and_prompt_isolation(tmp_path: Path) -> None:
    subject, exp, a, b = campaign(tmp_path)
    assert subject.protocol.schema_version == PROTOCOL_SCHEMA
    assert MIN_TRIALS == 2 and MAX_TRIALS == 32
    assert subject.store.protocol_path(subject.protocol.campaign_id).exists()
    first = subject.run_next_trial(); second = subject.run_next_trial()
    assert first["trial_id"] == "trial-1" and second["trial_id"] == "trial-2"
    assert first["observations"][0]["correlation_id"] != second["observations"][0]["correlation_id"]
    assert a.calls[0]["prompt"] == a.calls[3]["prompt"]
    assert "trial-1" not in a.calls[0]["prompt"] and "trial-2" not in a.calls[3]["prompt"]
    assert first["observations"][0]["authority_record_digest"] == exp.protocol.model_a_identity.authority_record_digest
    assert "authority_map_digest" not in first["observations"][0]


def test_reconstruction_between_completed_trials(tmp_path: Path) -> None:
    subject, exp, _, _ = campaign(tmp_path)
    subject.run_next_trial()
    restored = DevelopmentalModelReplacementCampaign.reconstruct(
        experiment=exp, artifact_root=tmp_path, campaign_id=subject.protocol.campaign_id)
    assert restored.state["next_trial_id"] == "trial-2"
    restored.run_next_trial()
    with pytest.raises(DevelopmentalModelReplacementError, match="already_complete"):
        restored.run_next_trial()
    assert restored.summarize()["completed_valid_trial_count"] == 2


def test_exact_descriptive_aggregation(tmp_path: Path) -> None:
    subject, _, _, _ = campaign(tmp_path)
    subject.run_next_trial(); subject.run_next_trial()
    report = subject.summarize()
    assert report["schema_version"] == REPORT_SCHEMA
    assert report["classification_counts"] == {"history_association_observed_under_both_cognitive_models": 2}
    assert report["history_effect_model_a_observed_count"] == 2
    assert report["history_effect_model_b_observed_count"] == 2
    assert report["history_association_under_both_models_count"] == 2
    assert report["model_a_restoration_stable_count"] == 2
    assert report["all_condition_output_digests_identical_across_trials"]
    serialized = json.dumps(report).lower()
    assert all(term not in serialized for term in ("p-value", "confidence interval", "posterior"))


@pytest.mark.parametrize(("a_effect", "b_effect", "expected"), [
    (False, False, "no_observable_history_effect_either_model"),
    (True, False, "history_association_observed_model_a_only"),
    (False, True, "history_association_observed_model_b_only"),
    (True, True, "history_association_observed_under_both_cognitive_models"),
])
def test_valid_negative_and_association_campaigns(tmp_path: Path, a_effect: bool, b_effect: bool, expected: str) -> None:
    subject, _, _, _ = campaign(tmp_path, a_effect=a_effect, b_effect=b_effect)
    subject.run_next_trial(); subject.run_next_trial()
    report = subject.summarize()
    assert report["classification_counts"] == {expected: 2}
    assert report["validity"] == "valid_completed_replication_campaign"


def test_trial_inventory_is_fixed_and_bounded(tmp_path: Path) -> None:
    exp = experiment(tmp_path)[0]
    for ids in (("only",), tuple(f"t-{i}" for i in range(33)), ("same", "same")):
        with pytest.raises(DevelopmentalModelReplacementError, match="inventory"):
            DevelopmentalModelReplacementCampaign.create(experiment=exp, artifact_root=tmp_path, trial_ids=ids)


def test_interrupted_trial_is_not_replayed(tmp_path: Path) -> None:
    subject, exp, _, _ = campaign(tmp_path)
    subject.state = subject.store.write_state(subject.protocol, {**subject.state, "in_progress_trial_id": "trial-1"})
    with pytest.raises(DevelopmentalModelReplacementError, match="interrupted"):
        DevelopmentalModelReplacementCampaign.reconstruct(experiment=exp, artifact_root=tmp_path,
                                                            campaign_id=subject.protocol.campaign_id)
    state = subject.store.load_state(subject.protocol)
    assert state["validity"] == "invalid_incomplete" and state["failure_reason"] == "campaign_interrupted_during_trial"


@pytest.mark.parametrize("target", ["state", "protocol"])
def test_campaign_protocol_and_state_tampering_fail_closed(tmp_path: Path, target: str) -> None:
    subject, exp, _, _ = campaign(tmp_path)
    path = subject.store.state_path(subject.protocol.campaign_id) if target == "state" else subject.store.protocol_path(subject.protocol.campaign_id)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(DevelopmentalModelReplacementError):
        DevelopmentalModelReplacementCampaign.reconstruct(experiment=exp, artifact_root=tmp_path,
                                                            campaign_id=subject.protocol.campaign_id)


def test_context_model_and_provenance_drift_fail_closed(tmp_path: Path) -> None:
    subject, exp, _, _ = campaign(tmp_path)
    exp.context = replace(exp.context, current_projection_digest="sha256:drift")
    with pytest.raises(DevelopmentalModelReplacementError): subject.run_next_trial()


def test_tampered_trial_artifact_is_rejected_by_aggregation(tmp_path: Path) -> None:
    subject, exp, _, _ = campaign(tmp_path)
    first = subject.run_next_trial(); subject.run_next_trial()
    (exp.store.runs / f"{first['run_id']}.json").write_text("{}", encoding="utf-8")
    with pytest.raises(DevelopmentalModelReplacementError, match="artifact_tampered"):
        subject.summarize()
