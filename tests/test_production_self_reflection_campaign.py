from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

import sentientosd

from sentientos import production_self_reflection_campaign as campaign_module
from sentientos.local_model_authority import digest_payload
from sentientos.production_self_reflection_campaign import (
    COMPONENTS, ProductionSelfReflectionCampaign, ProductionSelfReflectionError,
    ProductionSelfReflectionProtocol, reconstruct_protocol, verify_production_readiness,
    make_trial_receipt, verify_trial_receipt, ProductionSelfReflectionTransitionBindingObserver,
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


def _protocol(software_generation: str = "generation-1") -> ProductionSelfReflectionProtocol:
    return ProductionSelfReflectionProtocol.create(installation_identity="installation-1", software_generation=software_generation,
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


@pytest.mark.parametrize(
    ("readiness_case", "error_code"),
    [("tampered", "readiness_tampered"), ("wrong_protocol", "readiness_protocol_mismatch"),
     ("not_ready", "production_trial_not_ready"), ("unbound", "readiness_tampered")],
)
def test_run_one_requires_digest_valid_protocol_bound_readiness(
    tmp_path: Path, readiness_case: str, error_code: str,
) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    if readiness_case == "wrong_protocol":
        readiness = verify_production_readiness(_protocol("generation-2"), _observed())
    elif readiness_case == "not_ready":
        readiness = verify_production_readiness(protocol, _observed(model_a_available=False))
    elif readiness_case == "unbound":
        readiness = {"status": "production_trial_ready"}
    else:
        readiness = dict(verify_production_readiness(protocol, _observed()))
        readiness["readiness_digest"] = "sha256:replaced"

    executor_calls = []
    with pytest.raises(ProductionSelfReflectionError, match=error_code):
        campaign.run_one(readiness, lambda *args: executor_calls.append(args) or _evidence())

    assert executor_calls == []
    assert campaign.state()["completed_trials"] == []


def test_run_one_rejects_mutated_nested_protocol_before_executor(tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    protocol.model_a["cognitive_identity"] = "cognitive-substituted"
    executor_calls = []

    with pytest.raises(ProductionSelfReflectionError, match="protocol_tampered"):
        campaign.run_one(readiness, lambda *args: executor_calls.append(args) or _evidence())

    assert executor_calls == []
    raw_state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw_state["completed_trials"] == []
    assert raw_state["in_progress_trial_id"] is None


def test_run_one_uses_private_protocol_snapshot_across_preflight_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, _protocol())
    readiness = verify_production_readiness(campaign.protocol, _observed())
    original_verify = campaign_module._verify_readiness_binding

    def verify_then_mutate(protocol, receipt):
        original_verify(protocol, receipt)
        campaign.protocol.model_a["cognitive_identity"] = "concurrent-substitution"

    monkeypatch.setattr(campaign_module, "_verify_readiness_binding", verify_then_mutate)
    executor_identities = []

    campaign.run_one(
        readiness,
        lambda _trial, protocol: executor_identities.append(protocol.model_a["cognitive_identity"]) or _evidence(),
    )

    assert executor_identities == ["cognitive-a"]
    raw_state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw_state["completed_trials"][0]["trial_id"] == "trial-1"


@pytest.mark.parametrize("trial_count", [1, 2])
def test_campaign_reentry_preserves_partial_and_completed_progress(tmp_path: Path, trial_count: int) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    for _ in range(trial_count):
        campaign.run_one(readiness, lambda *_: _evidence())
    before = dict(campaign.state())

    resumed = ProductionSelfReflectionCampaign.create(tmp_path, protocol)

    assert dict(resumed.state()) == before
    assert len(resumed.state()["completed_trials"]) == trial_count
    if trial_count == 1:
        assert resumed.state()["next_trial_id"] == "trial-2"
        resumed.run_one(readiness, lambda *_: _evidence())
        assert resumed.state()["validity"] == "valid_complete"
    else:
        assert resumed.state()["validity"] == "valid_complete"


def test_campaign_reentry_does_not_reinitialize_missing_progress(tmp_path: Path) -> None:
    protocol = _protocol()
    ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    (tmp_path / "state.json").unlink()

    with pytest.raises(ProductionSelfReflectionError, match="campaign_state_unavailable"):
        ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    assert not (tmp_path / "state.json").exists()


def test_campaign_reentry_rejects_non_object_state_without_reinitializing(tmp_path: Path) -> None:
    protocol = _protocol()
    ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    state_path = tmp_path / "state.json"
    state_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ProductionSelfReflectionError, match="campaign_state_tampered"):
        ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    assert state_path.read_text(encoding="utf-8") == "[]"


def test_campaign_reentry_revalidates_completed_receipt_custody(tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    campaign.run_one(verify_production_readiness(protocol, _observed()), lambda *_: _evidence())
    receipt_path = tmp_path / "receipts" / "trial-1.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["protocol_digest"] = "sha256:stale-protocol"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ProductionSelfReflectionError, match="trial_receipt_tampered"):
        ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    assert campaign.state()["completed_trials"][0]["trial_id"] == "trial-1"


@pytest.mark.parametrize(
    ("receipt_change", "error_code"),
    [("missing", "campaign_receipt_unavailable"), ("tampered", "trial_receipt_tampered")],
)
def test_run_one_revalidates_prior_receipt_before_starting_next_trial(
    tmp_path: Path, receipt_change: str, error_code: str,
) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    campaign.run_one(readiness, lambda *_: _evidence())
    receipt_path = tmp_path / "receipts" / "trial-1.json"
    if receipt_change == "missing":
        receipt_path.unlink()
    else:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["protocol_digest"] = "sha256:replaced"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    executor_calls = []
    with pytest.raises(ProductionSelfReflectionError, match=error_code):
        campaign.run_one(readiness, lambda *args: executor_calls.append(args) or _evidence())

    assert executor_calls == []
    assert campaign.state()["next_trial_id"] == "trial-2"


@pytest.mark.parametrize(
    ("receipt_change", "error_code"),
    [("missing", "campaign_receipt_unavailable"), ("tampered", "trial_receipt_tampered")],
)
def test_report_revalidates_every_completed_receipt(
    tmp_path: Path, receipt_change: str, error_code: str,
) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    campaign.run_one(readiness, lambda *_: _evidence())
    campaign.run_one(readiness, lambda *_: _evidence())
    receipt_path = tmp_path / "receipts" / "trial-1.json"
    if receipt_change == "missing":
        receipt_path.unlink()
    else:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["protocol_digest"] = "sha256:replaced"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ProductionSelfReflectionError, match=error_code):
        campaign.report()
    assert not (tmp_path / "report.json").exists()


def test_report_uses_receipts_from_the_verified_lineage_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    campaign.run_one(readiness, lambda *_: _evidence())
    campaign.run_one(readiness, lambda *_: _evidence())
    original_verify = campaign._verify_progress

    def verify_then_replace_receipt(state):
        verified_receipts = original_verify(state)
        changed_evidence = _evidence()
        changed_evidence["condition_answers"] = {
            condition: [{"question_id": "claim:c1:classification", "answer": "unknown",
                         "claim_ids": ["c1"], "source_evidence_ids": ["e1"]}]
            for condition in CONDITION_ORDER
        }
        replacement = make_trial_receipt(protocol, "trial-1", changed_evidence)
        (tmp_path / "receipts" / "trial-1.json").write_text(
            json.dumps(replacement), encoding="utf-8"
        )
        return verified_receipts

    monkeypatch.setattr(campaign, "_verify_progress", verify_then_replace_receipt)

    report = campaign.report()

    for condition in CONDITION_ORDER:
        assert [row["supported_correct"] for row in report["condition_scores"][condition]] == [1, 1]


def test_reconstruction_waits_for_live_trial_before_classifying_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    entered = threading.Event()
    release = threading.Event()
    reconstruction_read = threading.Event()
    executor_calls = []

    original_state = ProductionSelfReflectionCampaign.state

    def observe_reconstruction_state(owner):
        if owner is not campaign:
            reconstruction_read.set()
        return original_state(owner)

    monkeypatch.setattr(ProductionSelfReflectionCampaign, "state", observe_reconstruction_state)

    def executor(trial_id, _protocol):
        executor_calls.append(trial_id)
        entered.set()
        assert release.wait(timeout=5)
        return _evidence()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(campaign.run_one, readiness, executor)
        assert entered.wait(timeout=5)
        reconstruction = pool.submit(ProductionSelfReflectionCampaign.reconstruct, tmp_path)
        assert not reconstruction_read.wait(timeout=0.1)
        release.set()
        first.result(timeout=5)
        resumed = reconstruction.result(timeout=5)

    assert executor_calls == ["trial-1"]
    assert resumed.state()["completed_trials"][0]["trial_id"] == "trial-1"
    assert resumed.state()["validity"] == "valid_incomplete"


def test_process_death_releases_campaign_lock_and_preserves_no_retry(tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_text(json.dumps(dict(verify_production_readiness(protocol, _observed()))), encoding="utf-8")
    script = (
        "import os, sys, json; from pathlib import Path; "
        "from sentientos.production_self_reflection_campaign import "
        "ProductionSelfReflectionCampaign, reconstruct_protocol; "
        "root = Path(sys.argv[1]); "
        "protocol = reconstruct_protocol(__import__('json').loads((root / 'protocol.json').read_text())); "
        "campaign = ProductionSelfReflectionCampaign(root, protocol); "
        "readiness = json.loads(Path(sys.argv[2]).read_text()); "
        "campaign.run_one(readiness, lambda *_: os._exit(73))"
    )

    child = subprocess.run([sys.executable, "-c", script, str(tmp_path), str(readiness_path)], check=False)

    assert child.returncode == 73
    with pytest.raises(ProductionSelfReflectionError, match="prior_trial_interrupted"):
        ProductionSelfReflectionCampaign.reconstruct(tmp_path)
    recovered = campaign.state()
    assert recovered["validity"] == "invalid_interrupted"
    assert recovered["failure_reason"] == "prior_trial_interrupted"
    assert not (tmp_path / "receipts" / "trial-1.json").exists()


@pytest.mark.parametrize("contradiction", ["reordered", "duplicate", "next_trial"])
def test_run_and_report_reject_contradictory_completion_lineage(
    tmp_path: Path, contradiction: str,
) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    campaign.run_one(readiness, lambda *_: _evidence())
    campaign.run_one(readiness, lambda *_: _evidence())
    state = dict(campaign.state())
    completed = list(state["completed_trials"])
    if contradiction == "reordered":
        state["completed_trials"] = list(reversed(completed))
    elif contradiction == "duplicate":
        state["completed_trials"] = [completed[0], completed[0]]
    else:
        state["next_trial_id"] = "trial-1"
    campaign._write(state)

    with pytest.raises(ProductionSelfReflectionError, match="campaign_state_tampered"):
        campaign.run_one(readiness, lambda *_: _evidence())
    with pytest.raises(ProductionSelfReflectionError, match="campaign_state_tampered"):
        campaign.report()


def test_run_and_report_preserve_interrupted_trial_no_retry(tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    state = dict(campaign.state())
    campaign._write({**state, "in_progress_trial_id": "trial-1"})
    executor_calls = []

    with pytest.raises(ProductionSelfReflectionError, match="campaign_not_runnable"):
        campaign.run_one(readiness, lambda *args: executor_calls.append(args) or _evidence())
    with pytest.raises(ProductionSelfReflectionError, match="campaign_incomplete"):
        campaign.report()

    assert executor_calls == []
    assert campaign.state()["in_progress_trial_id"] == "trial-1"


def test_completed_campaign_report_succeeds_after_lineage_revalidation(tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    readiness = verify_production_readiness(protocol, _observed())
    campaign.run_one(readiness, lambda *_: _evidence())
    campaign.run_one(readiness, lambda *_: _evidence())

    report = campaign.report()

    assert report["planned_trial_count"] == 2
    assert report["valid_completed_trials"] == 2
    assert all(len(report["condition_scores"][condition]) == 2 for condition in CONDITION_ORDER)
    assert report["unsupported_inferences"] == [
        "consciousness", "identity", "learning", "sentience", "guaranteed_improvement",
    ]


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


def test_readiness_artifact_publication_rejects_symlink_and_content_collision(tmp_path: Path) -> None:
    protocol = _protocol()
    observed = _observed(model_a_available=False)
    readiness = verify_production_readiness(protocol, observed)
    link = tmp_path / "readiness-link.json"
    target = tmp_path / "target.json"
    target.write_text(json.dumps(dict(readiness), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target.chmod(0o600)
    link.symlink_to(target)

    with pytest.raises(ProductionSelfReflectionError, match="immutable_artifact_tampered"):
        verify_production_readiness(protocol, observed, artifact_path=link)

    path = tmp_path / "readiness.json"
    verify_production_readiness(protocol, observed, artifact_path=path)
    with pytest.raises(ProductionSelfReflectionError, match="immutable_artifact_collision"):
        verify_production_readiness(protocol, _observed(model_b_available=False), artifact_path=path)


def test_readiness_artifact_concurrent_publication_is_first_writer_immutable(tmp_path: Path) -> None:
    protocol = _protocol()
    barrier = threading.Barrier(2)
    path = tmp_path / "readiness.json"

    def publish(observed):
        barrier.wait()
        return verify_production_readiness(protocol, observed, artifact_path=path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(publish, _observed(model_a_available=True)),
                   pool.submit(publish, _observed(model_a_available=False))]
        successes = []
        failures = []
        for future in futures:
            try:
                successes.append(future.result())
            except ProductionSelfReflectionError as exc:
                failures.append(exc.code)

    assert len(successes) == 1
    assert failures == ["immutable_artifact_collision"]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["readiness_digest"] == successes[0]["readiness_digest"]


def test_negative_and_null_scores_are_valid_evidence(tmp_path: Path) -> None:
    evidence = _evidence(); evidence["condition_answers"] = {condition: [] for condition in CONDITION_ORDER}
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, _protocol())
    receipt = campaign.run_one(verify_production_readiness(campaign.protocol, _observed()), lambda *_: evidence)
    assert receipt["status"] == "completed" and all(receipt["condition_scores"][c]["counts"]["supported_correct"] == 0 for c in CONDITION_ORDER)


def test_transition_binding_observer_is_read_only_and_exact(tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path / "campaign", protocol)
    owner_protocol = {"protocol_id": "transition-1", "protocol_digest": "transition-digest-1",
        "installation_identity": "installation-1", "journal_identity": "journal-1", "phase_order": PHASES}
    runtime = SimpleNamespace(
        config=SimpleNamespace(protocol_id="transition-1", protocol_digest="transition-digest-1",
            installation_identity="installation-1", journal_identity="journal-1"),
        controller=SimpleNamespace(protocol=SimpleNamespace(value=owner_protocol)),
        status=lambda: {"protocol_id": "transition-1", "protocol_digest": "transition-digest-1",
            "current_phase": PHASES[0], "current_journal_head": "journal-head-1",
            "interrupted": False, "outstanding_stage": None, "replay_forbidden": False},
        inspect_custody=lambda: {"read_only": True, "effect_performed": False, "request_count": 0},
        process_one=lambda: pytest.fail("binding inspection must not process operator requests"),
    )
    before = dict(campaign.state())
    result = ProductionSelfReflectionTransitionBindingObserver(campaign, runtime).inspect()
    assert result["status"] == "transition_binding_verified"
    assert all(result["checks"].values())
    assert result["effect_performed"] is False
    assert result["campaign_advanced"] is False
    assert result["grants_authority"] is False
    assert result["execution_allowed"] is False
    assert dict(campaign.state()) == before

    mismatched = SimpleNamespace(**vars(runtime))
    mismatched.config = SimpleNamespace(**vars(runtime.config))
    mismatched.config.protocol_digest = "different-transition-digest"
    blocked = ProductionSelfReflectionTransitionBindingObserver(campaign, mismatched).inspect()
    assert blocked["status"] == "transition_binding_unverified"
    assert blocked["checks"]["campaign_transition_protocol_digest"] is False
    assert blocked["execution_allowed"] is False
    assert dict(campaign.state()) == before


def test_read_only_campaign_open_preserves_pending_trial_and_never_waits(tmp_path: Path) -> None:
    campaign = ProductionSelfReflectionCampaign.create(tmp_path / "campaign", _protocol())
    state = dict(campaign.state())
    campaign._write({**state, "in_progress_trial_id": "trial-1"})
    before = dict(campaign.state())

    observed = ProductionSelfReflectionCampaign.open_for_read_only_inspection(campaign.root)
    assert dict(observed.state()) == before
    assert dict(campaign.state()) == before
    with campaign._campaign_lock():
        with pytest.raises(ProductionSelfReflectionError, match="campaign_busy"):
            ProductionSelfReflectionCampaign.open_for_read_only_inspection(campaign.root)


def test_daemon_projects_read_only_campaign_transition_binding(tmp_path: Path, monkeypatch) -> None:
    campaign_root = tmp_path / "campaign"
    campaign = ProductionSelfReflectionCampaign.create(campaign_root, _protocol())
    before = dict(campaign.state())
    owner_protocol = {"protocol_id": "transition-1", "protocol_digest": "transition-digest-1",
        "installation_identity": "installation-1", "journal_identity": "journal-1",
        "phase_order": PHASES}
    calls = {"process_one": 0}

    def process_one():
        calls["process_one"] += 1
        return {"status": "no_request", "effect_performed": False}

    runtime = SimpleNamespace(
        config=SimpleNamespace(protocol_id="transition-1", protocol_digest="transition-digest-1",
            installation_identity="installation-1", journal_identity="journal-1"),
        controller=SimpleNamespace(protocol=SimpleNamespace(value=owner_protocol)),
        status=lambda: {"protocol_id": "transition-1", "protocol_digest": "transition-digest-1",
            "current_phase": PHASES[0], "current_journal_head": "journal-head-1",
            "interrupted": False, "outstanding_stage": None, "replay_forbidden": False},
        inspect_custody=lambda: {"read_only": True, "effect_performed": False, "request_count": 0},
        process_one=process_one,
    )
    surfaces = sentientosd.RuntimeMaintenanceSurfaces.__new__(sentientosd.RuntimeMaintenanceSurfaces)
    surfaces._resident_transition_configuration_error = None
    surfaces._resident_transition_runtime = runtime
    surfaces._feedback = {}
    monkeypatch.setenv("SENTIENTOS_PRODUCTION_SELF_REFLECTION_CAMPAIGN_ROOT", str(campaign_root))

    result = surfaces.process_resident_cognitive_transition_request(tick_id="tick-1")
    binding = result["self_reflection_transition_binding"]
    assert calls["process_one"] == 1
    assert binding["status"] == "transition_binding_verified"
    assert binding["effect_performed"] is False
    assert binding["campaign_advanced"] is False
    assert binding["grants_authority"] is False
    assert binding["execution_allowed"] is False
    assert dict(campaign.state()) == before



def _verified_transition_stage_projection(
        protocol, phase: str, *, campaign_trial_id: str | None = "trial-1") -> dict[str, object]:
    transition = protocol.transition
    body: dict[str, object] = {
        "schema_version": "sentientos.resident_cognitive_transition_verified_stage_receipt:v3",
        "request_id": "resident-transition-request-planning",
        "campaign_trial_id": campaign_trial_id,
        "request_digest": "request-digest",
        "installation_identity": protocol.installation_identity,
        "protocol_id": transition["protocol_id"],
        "protocol_digest": transition["protocol_digest"],
        "phase": phase,
        "operator_receipt_digest": "operator-receipt-digest",
        "attempt_entry_digest": "attempt-entry-digest",
        "completed_entry_digest": "completed-entry-digest",
        "journal_head_observed": "completed-entry-digest",
        "operator_authentication": {
            "schema_version": "sentientos.resident_cognitive_transition_operator_authentication_binding:v1",
            "operator_identity": "operator-1",
            "signing_key_id": "ed25519-sha256:" + "a" * 64,
            "request_claims_digest": "sha256:" + "b" * 64,
            "provenance_digest": "sha256:" + "c" * 64,
            "signed_at": "2026-09-25T11:30:00Z",
            "trust_catalog_version": 1,
            "trust_catalog_digest": "sha256:" + "d" * 64,
        },
        "read_only": True,
        "effect_performed": False,
        "grants_authority": False,
        "execution_allowed": False,
    }
    body["binding_digest"] = hashlib.sha256(
        (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()
    return body


def test_verified_transition_receipt_plans_next_stage_without_execution(tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    projection = _verified_transition_stage_projection(protocol, PHASES[2])

    class TransitionOwner:
        def __init__(self) -> None:
            self.config = SimpleNamespace(
                installation_identity=protocol.installation_identity,
                protocol_id=protocol.transition["protocol_id"],
                protocol_digest=protocol.transition["protocol_digest"],
                journal_identity=protocol.transition["journal_identity"],
            )
            self.controller = SimpleNamespace(protocol=SimpleNamespace(value={
                "installation_identity": protocol.installation_identity,
                "protocol_id": protocol.transition["protocol_id"],
                "protocol_digest": protocol.transition["protocol_digest"],
                "journal_identity": protocol.transition["journal_identity"],
                "phase_order": protocol.transition["phase_order"],
            }))
            self.receipt_requests: list[str] = []
            self.current_phase = PHASES[2]
            self.journal_head = "completed-entry-digest"

        def inspect_verified_stage_receipt(self, request_id: str):
            self.receipt_requests.append(request_id)
            return MappingProxyType(dict(projection))

        def status(self):
            return {
                "protocol_id": protocol.transition["protocol_id"],
                "protocol_digest": protocol.transition["protocol_digest"],
                "current_phase": self.current_phase,
                "current_journal_head": self.journal_head,
                "interrupted": False,
                "outstanding_stage": None,
                "replay_forbidden": False,
                "semantically_verified_stage_entry_digests": ["completed-entry-digest"],
            }

    owner = TransitionOwner()
    before = dict(campaign.state())
    plan = ProductionSelfReflectionTransitionBindingObserver(
        campaign, owner).plan_next_stage("resident-transition-request-planning")

    assert plan["status"] == "next_stage_planned"
    assert plan["prior_stage"] == PHASES[2]
    assert plan["next_stage"] == PHASES[3]
    assert plan["campaign_next_trial_id"] == "trial-1"
    assert plan["campaign_trial_binding"] == "not_established_by_transition_receipt"
    assert plan["operator_authentication"] == projection["operator_authentication"]
    with pytest.raises(TypeError):
        plan["operator_authentication"]["operator_identity"] = "substituted"
    assert plan["campaign_trial_in_progress"] is False
    assert plan["next_stage_requires_separately_supplied_approval"] is True
    assert plan["read_only"] is True
    assert plan["effect_performed"] is False
    assert plan["campaign_advanced"] is False
    assert plan["grants_authority"] is False
    assert plan["execution_allowed"] is False
    assert "approval" not in plan
    assert owner.receipt_requests == ["resident-transition-request-planning"]
    assert dict(campaign.state()) == before


def test_transition_stage_plan_rejects_tampering_and_stale_owner(tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path, protocol)
    projection = _verified_transition_stage_projection(protocol, PHASES[2])

    class TransitionOwner:
        config = SimpleNamespace(
            installation_identity=protocol.installation_identity,
            protocol_id=protocol.transition["protocol_id"],
            protocol_digest=protocol.transition["protocol_digest"],
            journal_identity=protocol.transition["journal_identity"],
        )
        controller = SimpleNamespace(protocol=SimpleNamespace(value={
            "installation_identity": protocol.installation_identity,
            "protocol_id": protocol.transition["protocol_id"],
            "protocol_digest": protocol.transition["protocol_digest"],
            "journal_identity": protocol.transition["journal_identity"],
            "phase_order": protocol.transition["phase_order"],
        }))

        def __init__(self, receipt):
            self.receipt = receipt
            self.current_phase = PHASES[2]
            self.journal_head = "completed-entry-digest"
            self.semantic_entries = ["completed-entry-digest"]

        def inspect_verified_stage_receipt(self, _request_id):
            return self.receipt

        def status(self):
            return {
                "protocol_id": protocol.transition["protocol_id"],
                "protocol_digest": protocol.transition["protocol_digest"],
                "current_phase": self.current_phase,
                "current_journal_head": self.journal_head,
                "interrupted": False,
                "outstanding_stage": None,
                "replay_forbidden": False,
                "semantically_verified_stage_entry_digests": self.semantic_entries,
            }

    tampered = {**projection, "binding_digest": "0" * 64}
    with pytest.raises(ProductionSelfReflectionError,
                       match="transition_stage_receipt_binding_invalid"):
        ProductionSelfReflectionTransitionBindingObserver(
            campaign, TransitionOwner(tampered)).plan_next_stage(projection["request_id"])

    malformed_authentication = {
        **projection,
        "operator_authentication": {
            **projection["operator_authentication"],
            "signing_key_id": "unverified-key",
        },
    }
    malformed_authentication.pop("binding_digest")
    malformed_authentication["binding_digest"] = hashlib.sha256(
        (json.dumps(malformed_authentication, sort_keys=True, separators=(",", ":")) + "\n")
        .encode("utf-8")
    ).hexdigest()
    with pytest.raises(ProductionSelfReflectionError,
                       match="transition_stage_receipt_authentication_invalid"):
        ProductionSelfReflectionTransitionBindingObserver(
            campaign, TransitionOwner(malformed_authentication)).plan_next_stage(projection["request_id"])

    legacy_projection = {key: value for key, value in projection.items()
                         if key not in {"operator_authentication", "binding_digest"}}
    legacy_projection["schema_version"] = (
        "sentientos.resident_cognitive_transition_verified_stage_receipt:v2")
    legacy_projection["binding_digest"] = hashlib.sha256(
        (json.dumps(legacy_projection, sort_keys=True, separators=(",", ":")) + "\n")
        .encode("utf-8")
    ).hexdigest()
    with pytest.raises(ProductionSelfReflectionError,
                       match="transition_stage_receipt_binding_invalid"):
        ProductionSelfReflectionTransitionBindingObserver(
            campaign, TransitionOwner(legacy_projection)).plan_next_stage(projection["request_id"])

    stale_owner = TransitionOwner(projection)
    stale_owner.current_phase = PHASES[3]
    with pytest.raises(ProductionSelfReflectionError,
                       match="transition_stage_receipt_stale_or_unbound"):
        ProductionSelfReflectionTransitionBindingObserver(
            campaign, stale_owner).plan_next_stage(projection["request_id"])

    malformed_owner = TransitionOwner(projection)
    malformed_owner.semantic_entries = None
    with pytest.raises(ProductionSelfReflectionError,
                       match="transition_stage_receipt_stale_or_unbound"):
        ProductionSelfReflectionTransitionBindingObserver(
            campaign, malformed_owner).plan_next_stage(projection["request_id"])



def test_campaign_binds_verified_transition_plan_to_active_trial_without_authority(
        tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path / "campaign", protocol)
    active = {**dict(campaign.state()), "in_progress_trial_id": "trial-1"}
    campaign._write(active)
    projection = _verified_transition_stage_projection(protocol, PHASES[2])
    calls = {"process_one": 0}

    owner_protocol = {
        "installation_identity": protocol.installation_identity,
        "protocol_id": protocol.transition["protocol_id"],
        "protocol_digest": protocol.transition["protocol_digest"],
        "journal_identity": protocol.transition["journal_identity"],
        "phase_order": protocol.transition["phase_order"],
    }

    def forbidden_process_one():
        calls["process_one"] += 1
        raise AssertionError("campaign stage binding must not process requests")

    owner = SimpleNamespace(
        config=SimpleNamespace(
            installation_identity=protocol.installation_identity,
            protocol_id=protocol.transition["protocol_id"],
            protocol_digest=protocol.transition["protocol_digest"],
            journal_identity=protocol.transition["journal_identity"],
        ),
        controller=SimpleNamespace(protocol=SimpleNamespace(value=owner_protocol)),
        inspect_verified_stage_receipt=lambda request_id: MappingProxyType(dict(projection)),
        status=lambda: {
            "protocol_id": protocol.transition["protocol_id"],
            "protocol_digest": protocol.transition["protocol_digest"],
            "current_phase": PHASES[2],
            "current_journal_head": "completed-entry-digest",
            "interrupted": False,
            "outstanding_stage": None,
            "replay_forbidden": False,
            "semantically_verified_stage_entry_digests": ["completed-entry-digest"],
        },
        process_one=forbidden_process_one,
    )
    request_id = "resident-transition-request-planning"
    observer = ProductionSelfReflectionTransitionBindingObserver(campaign, owner)
    plan = observer.plan_next_stage(request_id)
    before = dict(campaign.state())

    binding = campaign.bind_verified_transition_plan_to_active_trial(
        plan, request_id=request_id, trial_id="trial-1", transition_owner=owner)

    assert binding["status"] == "active_trial_stage_bound"
    assert binding["campaign_trial_binding"] == "established_by_canonical_campaign_owner"
    assert binding["campaign_trial_id"] == "trial-1"
    assert binding["receipt_request_id"] == request_id
    assert binding["transition_plan_digest"] == plan["plan_digest"]
    assert binding["operator_authentication"] == plan["operator_authentication"]
    with pytest.raises(TypeError):
        binding["operator_authentication"]["operator_identity"] = "substituted"
    assert binding["next_stage"] == PHASES[3]
    assert binding["next_stage_requires_separately_supplied_approval"] is True
    assert binding["live_transition_owner_revalidation_required"] is True
    assert binding["read_only"] is True
    assert binding["effect_performed"] is False
    assert binding["campaign_advanced"] is False
    assert binding["grants_authority"] is False
    assert binding["execution_allowed"] is False
    assert "approval" not in binding
    assert calls["process_one"] == 0
    assert dict(campaign.state()) == before


def _assert_campaign_binds_verified_stage_receipt_to_active_trial(
        tmp_path: Path, phase: str) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path / "campaign", protocol)
    campaign._write({**dict(campaign.state()), "in_progress_trial_id": "trial-1"})
    projection = _verified_transition_stage_projection(protocol, phase)
    owner_protocol = {
        "installation_identity": protocol.installation_identity,
        "protocol_id": protocol.transition["protocol_id"],
        "protocol_digest": protocol.transition["protocol_digest"],
        "journal_identity": protocol.transition["journal_identity"],
        "phase_order": protocol.transition["phase_order"],
    }
    calls = {"inspect": 0, "process_one": 0}

    class TransitionOwner:
        config = SimpleNamespace(
            installation_identity=protocol.installation_identity,
            protocol_id=protocol.transition["protocol_id"],
            protocol_digest=protocol.transition["protocol_digest"],
            journal_identity=protocol.transition["journal_identity"],
        )
        controller = SimpleNamespace(protocol=SimpleNamespace(value=owner_protocol))

        def inspect_verified_stage_receipt(self, request_id):
            calls["inspect"] += 1
            assert request_id == projection["request_id"]
            return MappingProxyType(dict(projection))

        def status(self):
            return {
                "protocol_id": protocol.transition["protocol_id"],
                "protocol_digest": protocol.transition["protocol_digest"],
                "current_phase": phase,
                "current_journal_head": "completed-entry-digest",
                "interrupted": False,
                "outstanding_stage": None,
                "replay_forbidden": False,
                "semantically_verified_stage_entry_digests": [
                    "completed-entry-digest"],
            }

        def process_one(self):
            calls["process_one"] += 1
            raise AssertionError("binding must not process transition requests")

    owner = TransitionOwner()
    before = dict(campaign.state())
    binding = campaign.bind_verified_transition_stage_receipt_to_active_trial(
        request_id=projection["request_id"], trial_id="trial-1",
        transition_owner=owner)

    assert binding["status"] == "active_trial_stage_receipt_bound"
    assert binding["campaign_trial_id"] == "trial-1"
    assert binding["receipt_request_id"] == projection["request_id"]
    assert binding["receipt_binding_digest"] == projection["binding_digest"]
    assert binding["operator_receipt_digest"] == projection["operator_receipt_digest"]
    assert binding["attempt_entry_digest"] == projection["attempt_entry_digest"]
    assert binding["completed_entry_digest"] == projection["completed_entry_digest"]
    assert binding["phase"] == phase
    assert binding["operator_authentication"] == projection["operator_authentication"]
    with pytest.raises(TypeError):
        binding["operator_authentication"]["operator_identity"] = "substituted"
    assert binding["live_transition_owner_revalidation_required"] is True
    assert binding["read_only"] is True
    assert binding["effect_performed"] is False
    assert binding["campaign_advanced"] is False
    assert binding["grants_authority"] is False
    assert binding["execution_allowed"] is False
    assert binding["binding_digest"] == _d(campaign_module._json_value({
        key: value for key, value in binding.items() if key != "binding_digest"}))
    with pytest.raises(TypeError):
        binding["status"] = "substituted"
    assert calls["process_one"] == 0
    assert calls["inspect"] >= 2
    assert dict(campaign.state()) == before


def test_campaign_binds_verified_stage_receipt_to_active_trial_without_execution(
        tmp_path: Path) -> None:
    _assert_campaign_binds_verified_stage_receipt_to_active_trial(tmp_path, PHASES[2])


def test_campaign_binds_final_verified_stage_receipt_to_active_trial_without_execution(
        tmp_path: Path) -> None:
    _assert_campaign_binds_verified_stage_receipt_to_active_trial(tmp_path, PHASES[-1])


def test_campaign_stage_receipt_binding_rejects_changed_live_owner(
        tmp_path: Path) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path / "campaign", protocol)
    campaign._write({**dict(campaign.state()), "in_progress_trial_id": "trial-1"})
    projection = _verified_transition_stage_projection(protocol, PHASES[2])
    owner_protocol = {
        "installation_identity": protocol.installation_identity,
        "protocol_id": protocol.transition["protocol_id"],
        "protocol_digest": protocol.transition["protocol_digest"],
        "journal_identity": protocol.transition["journal_identity"],
        "phase_order": protocol.transition["phase_order"],
    }
    owner = SimpleNamespace(
        config=SimpleNamespace(
            installation_identity=protocol.installation_identity,
            protocol_id=protocol.transition["protocol_id"],
            protocol_digest=protocol.transition["protocol_digest"],
            journal_identity=protocol.transition["journal_identity"],
        ),
        controller=SimpleNamespace(protocol=SimpleNamespace(value=owner_protocol)),
        inspect_verified_stage_receipt=lambda _request_id: MappingProxyType(dict(projection)),
    )
    status_calls = {"count": 0}

    def changing_status():
        status_calls["count"] += 1
        return {
            "protocol_id": protocol.transition["protocol_id"],
            "protocol_digest": protocol.transition["protocol_digest"],
            "current_phase": PHASES[2],
            "current_journal_head": (
                "changed-journal-head" if status_calls["count"] >= 3
                else "completed-entry-digest"),
            "interrupted": False,
            "outstanding_stage": None,
            "replay_forbidden": False,
            "semantically_verified_stage_entry_digests": ["completed-entry-digest"],
        }

    owner.status = changing_status
    with pytest.raises(ProductionSelfReflectionError,
                       match="transition_stage_receipt_binding_stale_or_unbound"):
        campaign.bind_verified_transition_stage_receipt_to_active_trial(
            request_id=projection["request_id"], trial_id="trial-1",
            transition_owner=owner)


@pytest.mark.parametrize("failure", ["wrong_trial", "interrupted"])
def test_campaign_trial_binding_fails_closed_on_wrong_or_terminal_trial(
        tmp_path: Path, failure: str) -> None:
    protocol = _protocol()
    campaign = ProductionSelfReflectionCampaign.create(tmp_path / failure, protocol)
    active = {**dict(campaign.state()), "in_progress_trial_id": "trial-1"}
    campaign._write(active)
    projection = _verified_transition_stage_projection(
        protocol, PHASES[2],
        campaign_trial_id=None if failure == "unbound_request" else "trial-1")
    owner_protocol = {
        "installation_identity": protocol.installation_identity,
        "protocol_id": protocol.transition["protocol_id"],
        "protocol_digest": protocol.transition["protocol_digest"],
        "journal_identity": protocol.transition["journal_identity"],
        "phase_order": protocol.transition["phase_order"],
    }
    owner = SimpleNamespace(
        config=SimpleNamespace(
            installation_identity=protocol.installation_identity,
            protocol_id=protocol.transition["protocol_id"],
            protocol_digest=protocol.transition["protocol_digest"],
            journal_identity=protocol.transition["journal_identity"],
        ),
        controller=SimpleNamespace(protocol=SimpleNamespace(value=owner_protocol)),
        inspect_verified_stage_receipt=lambda _request_id: MappingProxyType(dict(projection)),
        status=lambda: {
            "protocol_id": protocol.transition["protocol_id"],
            "protocol_digest": protocol.transition["protocol_digest"],
            "current_phase": PHASES[2],
            "current_journal_head": "completed-entry-digest",
            "interrupted": False,
            "outstanding_stage": None,
            "replay_forbidden": False,
            "semantically_verified_stage_entry_digests": ["completed-entry-digest"],
        },
    )
    request_id = projection["request_id"]
    observer = ProductionSelfReflectionTransitionBindingObserver(campaign, owner)
    plan = observer.plan_next_stage(request_id)
    if failure == "interrupted":
        campaign._write({**dict(campaign.state()), "validity": "invalid_interrupted",
                         "failure_reason": "trial_interrupted_no_retry"})
        expected = "transition_stage_plan_tampered_or_stale"
    else:
        expected = "transition_stage_plan_not_for_active_trial"

    with pytest.raises(ProductionSelfReflectionError, match=expected):
        campaign.bind_verified_transition_plan_to_active_trial(
            plan, request_id=request_id,
            trial_id="trial-2" if failure == "wrong_trial" else "trial-1",
            transition_owner=owner)
