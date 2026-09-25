from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from sentientos.local_model_authority import digest_payload
from sentientos.production_self_reflection_campaign import (
    COMPONENTS, ProductionSelfReflectionCampaign, ProductionSelfReflectionError,
    ProductionSelfReflectionProtocol, reconstruct_protocol, verify_production_readiness,
    verify_trial_receipt,
)
from sentientos.resident_cognitive_model_transition_experiment import PHASES
from sentientos.self_model_intervention_experiment import CONDITION_ORDER

pytestmark = pytest.mark.no_legacy_skip


def _d(value) -> str:
    return "sha256:" + digest_payload(value)


ANSWER_KEY = {"claim:c1:classification": {"answer": "current", "claim_id": "c1", "source_evidence_ids": ("e1",)}}


def _model(name: str) -> dict[str, object]:
    return {"commissioning_receipt_id": f"commission-{name}", "commissioning_receipt_digest": f"sha256:{name * 64}",
        "cognitive_identity": f"cognitive-{name}", "artifact_digest": f"sha256:{name * 64}", "artifact_size": 100,
        "development_provenance_digest": f"sha256:{name * 63}p", "serving_configuration_digest": f"sha256:{name * 63}s",
        "activation_approval_id": f"activation-{name}", "serving_approval_id": f"serving-{name}",
        "inference_authority_map_id": f"authority-{name}"}


def _protocol() -> ProductionSelfReflectionProtocol:
    return ProductionSelfReflectionProtocol.create(installation_identity="installation-1", software_generation="generation-1",
        runtime_configuration={"backend": "real-local"}, model_a=_model("a"), model_b=_model("b"),
        persistent_state={"developmental_history_boundary_digest": "history-1", "composition_state_digest": "composition-1",
            "initial_reconciliation_id": "reconcile-1", "initial_reconciliation_digest": "reconcile-digest-1",
            "projection_policy": "prior-tick-only:v1", "assessment_claim_inventory_digest": "inventory-1",
            "world_state_id": "world-1", "world_state_digest": "world-digest-1"},
        assessment={"question_set_digest": "questions-1", "answer_key_digest": _d(ANSWER_KEY),
            "scorer_version": "deterministic_exact_evidence_key:v1", "scorer_digest": "scorer-1",
            "projection_id": "projection-1", "projection_digest": "projection-digest-1",
            "prompt_construction_digest": "prompt-1", "inference_budget": {"tokens": 10},
            "generation_parameters": {"temperature": 0}, "abstention_format": "abstain",
            "citation_format": "claim-and-source-ids", "condition_order": CONDITION_ORDER},
        transition={"protocol_id": "transition-1", "protocol_digest": "transition-digest-1", "phase_order": PHASES,
            "journal_custody": "state/resident-cognitive-transition/transition.journal.jsonl", "journal_identity": "journal-1",
            "installation_relative_custody": True, "quiescence_semantics": "no-inflight-token-bound",
            "subordinate_activation_approvals": ("activation-b", "activation-a"), "failure_posture": "interrupt_no_retry_no_rollback"},
        trial_ids=("trial-1", "trial-2"))


def _observed(**changes) -> dict[str, object]:
    value: dict[str, object] = {"installation_identity": "installation-1", "reconciliation_digest": "reconcile-digest-1",
        "developmental_history_boundary_digest": "history-1", "resident_cognitive_identity": "cognitive-a",
        "model_a_available": True, "model_b_available": True, "commissioning_valid": True, "model_artifacts_valid": True,
        "runtime_backend_available": True, "activation_approvals_valid": True, "serving_approvals_valid": True,
        "inference_admission_valid": True, "transition_protocol_digest": "transition-digest-1", "stable_serving_slot_valid": True,
        "live_quiescence_gate": True, "required_roots_available": True, "assessment_protocol_valid": True,
        "scorer_digest": "scorer-1", "campaign_state_valid": True, "prior_trial_interrupted": False,
        "transition_journal_interrupted": False, "canonical_state_conflict": False,
        "evidence_components": {key: "nonsynthetic" for key in COMPONENTS}}
    value.update(changes); return value


def _answers() -> list[dict[str, object]]:
    return [{"question_id": "claim:c1:classification", "answer": "current", "claim_ids": ["c1"], "source_evidence_ids": ["e1"]}]


def _evidence() -> dict[str, object]:
    return {"installation_identity": "installation-1", "software_generation_before": "generation-1",
        "software_generation_after": "generation-1", "transition_stage_receipts": [{"phase": p, "receipt_id": f"r-{n}"} for n, p in enumerate(PHASES[1:])],
        "transition_journal_identity": "journal-1", "world_state_identities": ["world-a", "world-b", "world-restored-a"],
        "self_model_reconciliations": ["reconcile-a", "reconcile-b", "reconcile-restored-a"],
        "self_model_projections": [{"projection_id": x, "source_tick": n, "consuming_tick": n + 1, "prior_tick_proven": True}
                                   for n, x in enumerate(("projection-a", "projection-b", "projection-restored-a"))],
        "developmental_history_boundary_digest": "history-1", "condition_inference_receipts":
            {condition: {"receipt_id": f"inference-{condition}", "receipt_digest": f"digest-{condition}"} for condition in CONDITION_ORDER},
        "condition_answers": {condition: _answers() for condition in CONDITION_ORDER}, "answer_key": ANSWER_KEY,
        "pre_resident_identity": "cognitive-a", "post_resident_identity": "cognitive-a",
        "pre_self_model_generation": 1, "post_self_model_generation": 3, "restoration_result": "exact_identity_restored",
        "evidence_components": {key: "nonsynthetic" for key in COMPONENTS}}


def test_production_readiness_success_and_synthetic_failure() -> None:
    protocol = _protocol(); ready = verify_production_readiness(protocol, _observed())
    assert ready["status"] == "production_trial_ready" and ready["classifications"] == ["production_trial_ready"]
    components = {key: "nonsynthetic" for key in COMPONENTS}; components["runtime_workers"] = "synthetic"
    blocked = verify_production_readiness(protocol, _observed(evidence_components=components))
    assert blocked["status"] == "production_trial_not_ready"
    assert blocked["classifications"] == ["synthetic_component_detected"]


def test_one_shot_exact_transition_firewall_external_scorer_and_restored_a(tmp_path: Path) -> None:
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, _protocol()); calls = []
    receipt = campaign.run_one(verify_production_readiness(campaign.protocol, _observed()),
                               lambda trial, protocol: calls.append(trial) or _evidence())
    assert calls == ["trial-1"] and campaign.state()["next_trial_id"] == "trial-2"
    assert [x["phase"] for x in receipt["transition_stage_receipts"]] == list(PHASES[1:])
    assert all(x["prior_tick_proven"] for x in receipt["self_model_projections"])
    assert receipt["model_output_has_scoring_authority"] is False
    assert receipt["post_resident_identity"] == "cognitive-a"
    assert all(receipt["condition_scores"][c]["counts"]["supported_correct"] == 1 for c in CONDITION_ORDER)


def test_interrupted_campaign_is_no_retry(tmp_path: Path) -> None:
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, _protocol())
    state = dict(campaign.state()); state["in_progress_trial_id"] = "trial-1"; campaign._write(state)
    with pytest.raises(ProductionSelfReflectionError, match="prior_trial_interrupted"):
        ProductionSelfReflectionCampaign.reconstruct(tmp_path)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["validity"] == "invalid_interrupted" and state["next_trial_id"] == "trial-1"
    assert json.loads((tmp_path / "failures/trial-1.json").read_text())["retry_permitted"] is False


def test_protocol_and_receipt_tamper_fail_reconstruction(tmp_path: Path) -> None:
    protocol = _protocol(); value = asdict(protocol); value["software_generation"] = "tampered"
    with pytest.raises(ProductionSelfReflectionError, match="protocol_tampered"): reconstruct_protocol(value)
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    receipt = dict(campaign.run_one(verify_production_readiness(protocol, _observed()), lambda *_: _evidence()))
    receipt["post_resident_identity"] = "cognitive-b"
    with pytest.raises(ProductionSelfReflectionError, match="trial_receipt_tampered"): verify_trial_receipt(receipt)


def test_missing_real_models_writes_precise_not_ready_artifact(tmp_path: Path) -> None:
    path = tmp_path / "readiness.json"
    result = verify_production_readiness(_protocol(), _observed(model_a_available=False, model_b_available=False), artifact_path=path)
    assert result["status"] == "production_trial_not_ready" and result["effect_performed"] is False
    assert "missing_model_a" in result["classifications"] and "missing_model_b" in result["classifications"]
    assert json.loads(path.read_text())["readiness_digest"] == result["readiness_digest"]


def test_negative_and_null_scores_are_valid_evidence(tmp_path: Path) -> None:
    evidence = _evidence(); evidence["condition_answers"] = {condition: [] for condition in CONDITION_ORDER}
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, _protocol())
    receipt = campaign.run_one(verify_production_readiness(campaign.protocol, _observed()), lambda *_: evidence)
    assert receipt["status"] == "completed" and all(receipt["condition_scores"][c]["counts"]["supported_correct"] == 0 for c in CONDITION_ORDER)
