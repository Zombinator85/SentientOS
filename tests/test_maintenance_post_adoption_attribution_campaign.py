from dataclasses import asdict, replace
import json

import pytest

from sentientos.governed_improvement_signal_plane import normalize_record
from sentientos.maintenance_post_adoption_attribution_campaign import (
    ATTRIBUTION_POSTURE, AttributionCampaignError, ControlDefinition,
    MaintenancePostAdoptionAttributionCampaignOwner, campaign_epistemic_binding,
    campaign_improvement_signal_record, developmental_evidence_record, digest,
    make_campaign_protocol, make_control_observation,
)
from sentientos.maintenance_post_adoption_evaluation import Evaluation, FALSE_AUTHORITY

pytestmark = pytest.mark.no_legacy_skip


def protocol(*, evidence_class="synthetic", task_id="task-1", proposal_id="proposal-1"):
    return make_campaign_protocol(maintenance_task_id=task_id, proposal_id=proposal_id, signal_ids=("signal-1",),
        predecessor_generation=4, predecessor_revision="a"*40, predecessor_tree="b"*40,
        successor_generation=5, successor_revision="c"*40, successor_tree="d"*40,
        adoption_identity="adoption:exact", evaluation_protocol_ids=("p1","p2"),
        evaluation_protocol_digests=("sha256:"+"1"*64,"sha256:"+"2"*64), target_observable_ids=("latency",),
        target_measurement_laws={"latency":"median-v1"}, protected_invariant_ids=("errors",),
        controls=(ControlDefinition("load","mean-v1","absolute_delta_lte_1","independent host collector",("host_observation",)),),
        control_design="matched_repeated_conditions", attribution_rule="all_trials_same_category_v1",
        trial_ids=("trial-1","trial-2"), minimum_trials=2, maximum_trials=2, evidence_class=evidence_class,
        created_at="2026-01-01T00:00:00Z", creation_generation=4, no_retry=True, no_replacement=True,
        no_cherry_picking=True)


def evaluation(p, order, result="target_expectation_satisfied"):
    raw = Evaluation("","",p.evaluation_protocol_ids[order],p.evaluation_protocol_digests[order],"task-1",
        "sha256:"+"3"*64,"sha256:"+str(order+4)*64,4,5,"a"*40,"c"*40,(),(),(),result,
        "controlled_before_after_correlation_not_experimental_causation",f"2026-01-0{order+2}T02:00:00Z",
        (p.adoption_identity,"sha256:"+str(order+6)*64),"sha256:"+"9"*64,dict(FALSE_AUTHORITY))
    return replace(raw,evaluation_id=f"evaluation-{order}",evaluation_digest=digest(raw.payload()))


def control(p, trial_id, *, match="matched", evidence_class=None):
    return make_control_observation(p,trial_id=trial_id,observable_id="load",measurement_law="mean-v1",
        matching_rule="absolute_delta_lte_1",match_result=match,before_value=10,after_value=10 if match=="matched" else 15,
        source_identity="host-sensor-1",source_digest="sha256:"+"e"*64,source_schema="sentientos.host_observation:v1",
        source_class="host_observation",observed_at="2026-01-02T01:00:00Z",collector_identity="collector-1",
        dependency_ids=("host:boot-1",),window_identity=f"window:{trial_id}",world_state_binding="world-state:1",
        host_observation_binding="host-observation:1",evidence_class=evidence_class or p.evidence_class)


def finish(tmp_path, outcomes, *, matches=None, evidence_class="synthetic", task_id="task-1", proposal_id="proposal-1"):
    owner=MaintenancePostAdoptionAttributionCampaignOwner(tmp_path); p=owner.preregister(protocol(evidence_class=evidence_class,
        task_id=task_id, proposal_id=proposal_id))
    matches=matches or ["matched"]*len(outcomes)
    for index, outcome in enumerate(outcomes):
        trial=p.trial_ids[index]; ev=None if outcome is None else evaluation(p,index,outcome)
        owner.record_trial(p,trial_id=trial,evaluation=ev,controls=(() if outcome=="missing_control" else (control(p,trial,match=matches[index]),)),
                           terminal_status="interrupted" if outcome is None else "completed",completed_at=f"2026-01-0{index+3}T00:00:00Z")
    return owner,p,owner.finalize(p,completed_at="2026-01-10T00:00:00Z")


def test_repeated_satisfied_under_independent_matched_controls_is_noncausal(tmp_path):
    owner,p,result=finish(tmp_path,["target_expectation_satisfied"]*2,evidence_class="production")
    assert result.classification == "repeated_association_under_matched_controls"
    assert result.attribution_posture == ATTRIBUTION_POSTURE and result.production_ready
    assert campaign_improvement_signal_record(result) is None
    assert MaintenancePostAdoptionAttributionCampaignOwner(tmp_path).result(p.campaign_id) == result
    assert owner.verify() == {"protocols":1,"controls":2,"trials":2,"results":1,"signals":0}


def test_environment_change_is_confound_not_association(tmp_path):
    _,_,result=finish(tmp_path,["target_expectation_satisfied"]*2,matches=["matched","out_of_envelope"])
    assert result.classification == "environmental_confound_detected"


def test_repeated_contradiction_retained_and_routes_distinct_proposal_only_signal(tmp_path):
    _,_,result=finish(tmp_path,["target_expectation_contradicted"]*2)
    signal=campaign_improvement_signal_record(result)
    assert result.classification == "repeated_target_contradiction_under_matched_controls"
    assert signal and signal["finding_kind"] == "recurring_failure" and signal["repository_mutation_performed"] is False
    assert normalize_record(signal).routing_eligible


def test_signal_projection_preserves_verified_lineage_and_classification_posture(tmp_path):
    owner, p, result = finish(tmp_path, ["target_expectation_contradicted"] * 2)
    signal = campaign_improvement_signal_record(result, protocol=owner.protocol(p.campaign_id),
        selection_config_digest=digest({"campaign_ids": [p.campaign_id]}))
    assert signal is not None
    refs = set(signal["evidence_refs"])
    assert "campaign_digest:" + result.campaign_digest in refs
    assert "result_digest:" + result.result_digest in refs
    assert {"evaluation_id:" + item for item in result.evaluation_ids} <= refs
    assert {"control_id:" + item for item in result.control_ids} <= refs
    assert "classification:" + result.classification in refs
    assert "source_posture:control_source_issuers_unverified" in refs
    assert "selection_campaign_id:" + p.campaign_id in refs
    assert "selection_config_digest:" + digest({"campaign_ids": [p.campaign_id]}) in refs
    assert "read_only_projection:true" in refs
    assert signal["observed_at"] == result.completed_at
    assert signal["severity"] == "medium"


def test_completed_positive_or_mixed_campaigns_are_diagnostic_only(tmp_path):
    _, _, positive = finish(tmp_path / "positive", ["target_expectation_satisfied"] * 2)
    _, _, mixed = finish(tmp_path / "mixed", ["target_expectation_satisfied", "target_expectation_contradicted"])
    _, _, protected = finish(tmp_path / "protected",
        ["target_expectation_satisfied", "new_regression_observed"])
    positive_signal = campaign_improvement_signal_record(positive)
    mixed_signal = campaign_improvement_signal_record(mixed)
    protected_signal = campaign_improvement_signal_record(protected)
    assert positive_signal is not None and positive_signal["finding_kind"] == "diagnostic"
    assert mixed_signal is not None and mixed_signal["finding_kind"] == "diagnostic"
    assert protected_signal is not None and protected_signal["finding_kind"] == "recurring_failure"
    assert protected_signal["severity"] == "high"
    assert protected.production_ready is False
    assert "source_posture:control_source_issuers_unverified" in protected_signal["evidence_refs"]
    assert normalize_record(positive_signal).severity == "medium"
    assert normalize_record(mixed_signal).severity == "medium"


def test_campaign_looking_json_is_not_an_authenticated_signal_artifact(tmp_path):
    from sentientos.governed_improvement_signal_plane import records_from_artifact

    path = tmp_path / "forged.json"
    path.write_text(json.dumps({"campaign_id": "attribution-campaign:" + "a" * 24,
        "classification": "protected_regression_observed", "severity": "high"}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown_artifact_source"):
        records_from_artifact("post_adoption_attribution_campaign", path, repo_root=tmp_path)


def test_runtime_campaign_selection_config_tampering_fails_closed(tmp_path):
    from sentientosd import _load_post_adoption_attribution_projection

    body = {"schema_version": "sentientos.post_adoption_attribution_world_state_projection:v1",
        "enabled": True, "store_root": str(tmp_path / "campaigns"),
        "campaign_ids": ["attribution-campaign:" + "a" * 24]}
    payload = {**body, "config_digest": digest(body)}
    payload["campaign_ids"] = []
    path = tmp_path / "tampered-projection.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    owner, campaign_ids, status = _load_post_adoption_attribution_projection(str(path))

    assert owner is None and campaign_ids == ()
    assert status["status"] == "invalid"
    assert status["effect_authority"] is False


def test_repeated_campaigns_deduplicate_and_contradictory_correction_stays_bounded(tmp_path):
    import subprocess
    import sys

    from sentientos.governed_improvement_signal_plane import evaluate_signal_plane

    first_owner, first_protocol, first = finish(tmp_path / "first",
        ["target_expectation_contradicted"] * 2, task_id="task-first")
    repeated_owner, repeated_protocol, repeated = finish(tmp_path / "repeated",
        ["target_expectation_contradicted"] * 2, task_id="task-repeated")
    correction_owner, correction_protocol, correction = finish(tmp_path / "correction",
        ["target_expectation_satisfied"] * 2, task_id="task-correction")
    confound_owner, confound_protocol, confound = finish(tmp_path / "confound",
        ["target_expectation_satisfied"] * 2, matches=["matched", "out_of_envelope"],
        task_id="task-confound")
    null_owner, null_protocol, null = finish(tmp_path / "null",
        [None, "target_expectation_contradicted"], task_id="task-null")
    inconclusive_owner, inconclusive_protocol, inconclusive = finish(tmp_path / "inconclusive",
        ["insufficient_evidence"] * 2, task_id="task-inconclusive")
    first_signal = campaign_improvement_signal_record(first, protocol=first_owner.protocol(first_protocol.campaign_id))
    repeated_signal = campaign_improvement_signal_record(repeated, protocol=repeated_owner.protocol(repeated_protocol.campaign_id))
    correction_signal = campaign_improvement_signal_record(correction,
        protocol=correction_owner.protocol(correction_protocol.campaign_id))
    confound_signal = campaign_improvement_signal_record(confound,
        protocol=confound_owner.protocol(confound_protocol.campaign_id))
    null_signal = campaign_improvement_signal_record(null,
        protocol=null_owner.protocol(null_protocol.campaign_id))
    inconclusive_signal = campaign_improvement_signal_record(inconclusive,
        protocol=inconclusive_owner.protocol(inconclusive_protocol.campaign_id))
    assert first_signal and repeated_signal and correction_signal
    assert confound_signal and null_signal and inconclusive_signal

    consistent = evaluate_signal_plane([first_signal, repeated_signal, first_signal], repo_root=tmp_path)
    assert consistent.batch.duplicate_signal_ids == (normalize_record(first_signal).signal_id,)
    assert not consistent.batch.contradiction_ids
    assert len(consistent.batch.signals) == 2

    conflicting = evaluate_signal_plane([first_signal, repeated_signal, correction_signal], repo_root=tmp_path)
    campaign_ids = {signal.signal_id for signal in conflicting.batch.signals}
    assert set(conflicting.batch.contradiction_ids) == campaign_ids
    assert {receipt.disposition for receipt in conflicting.receipts} == {"blocked_invalid"}
    assert all("classification:repeated_target_contradiction_under_matched_controls"
        in signal.evidence_refs or "classification:repeated_association_under_matched_controls"
        in signal.evidence_refs for signal in conflicting.batch.signals)
    assert evaluate_signal_plane([first_signal, repeated_signal, correction_signal],
        repo_root=tmp_path).batch.batch_id == conflicting.batch.batch_id

    confounded_plane = evaluate_signal_plane([confound_signal], repo_root=tmp_path)
    null_plane = evaluate_signal_plane([null_signal], repo_root=tmp_path)
    inconclusive_plane = evaluate_signal_plane([inconclusive_signal], repo_root=tmp_path)
    assert confounded_plane.receipts[0].disposition == "blocked_invalid"
    assert null_plane.receipts[0].disposition == "gap_seeker_diagnostic"
    assert inconclusive_plane.receipts[0].disposition == "blocked_invalid"
    assert not confounded_plane.amendment_inputs and not null_plane.amendment_inputs
    assert not inconclusive_plane.amendment_inputs

    script = (
        "import json,sys; from sentientos.maintenance_post_adoption_attribution_campaign import "
        "MaintenancePostAdoptionAttributionCampaignOwner as O; "
        "print(json.dumps([O(root,read_only=True).result(cid).classification "
        "for root,cid in zip(sys.argv[1::2],sys.argv[2::2])]))"
    )
    recovered = subprocess.run([sys.executable, "-c", script,
        str(tmp_path / "first"), first_protocol.campaign_id,
        str(tmp_path / "repeated"), repeated_protocol.campaign_id,
        str(tmp_path / "correction"), correction_protocol.campaign_id,
        str(tmp_path / "confound"), confound_protocol.campaign_id,
        str(tmp_path / "null"), null_protocol.campaign_id,
        str(tmp_path / "inconclusive"), inconclusive_protocol.campaign_id],
        check=True, capture_output=True, text=True)
    assert json.loads(recovered.stdout) == [
        "repeated_target_contradiction_under_matched_controls",
        "repeated_target_contradiction_under_matched_controls",
        "repeated_association_under_matched_controls",
        "environmental_confound_detected",
        "interrupted_or_invalid_trial",
        "insufficient_target_evidence",
    ]


def test_runtime_signal_plane_uses_only_selected_recovered_campaign_results(tmp_path, monkeypatch):
    from sentientosd import RuntimeMaintenanceSurfaces, _load_post_adoption_attribution_projection
    from sentientos.runtime_governor import reset_runtime_governor
    from sentientos.control_plane_kernel import (AuthorityClass, ControlActionRequest,
        ControlPlaneKernel, LifecyclePhase)

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    reset_runtime_governor()

    store = tmp_path / "campaign-store"
    writer, protocol_value, result = finish(store, ["target_expectation_contradicted"] * 2)
    projection_body = {"schema_version": "sentientos.post_adoption_attribution_world_state_projection:v1",
        "enabled": True, "store_root": str(store), "campaign_ids": [protocol_value.campaign_id]}
    projection_config = {**projection_body, "config_digest": digest(projection_body)}
    projection_path = tmp_path / "campaign-projection.json"
    projection_path.write_text(json.dumps(projection_config), encoding="utf-8")
    selected, selected_ids, projection_status = _load_post_adoption_attribution_projection(
        str(projection_path))
    config_digest = projection_config["config_digest"]
    assert selected is not None and selected_ids == (protocol_value.campaign_id,)
    assert selected.read_only is True and projection_status["status"] == "verified"
    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime",
        post_adoption_attribution_owner=selected,
        post_adoption_attribution_campaign_ids=selected_ids,
        post_adoption_attribution_projection_status=projection_status)
    class AllowProposalEvaluation:
        def admit_action(self, _action_class, _actor, correlation_id, *, metadata):
            return type("Decision", (), {"allowed": True, "reason": "fixture_admitted",
                "correlation_id": correlation_id, "to_dict": lambda self: {"allowed": True}})()

    kernel = ControlPlaneKernel(runtime_governor=AllowProposalEvaluation(),
        decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(LifecyclePhase.MAINTENANCE, actor="test")
    decision, evaluation_value = kernel.admit_and_execute(ControlActionRequest(
        action_kind="identify_improvement_signals", authority_class=AuthorityClass.PROPOSAL_EVALUATION,
        actor="test", target_subsystem="governed_improvement_signal_plane",
        requested_phase=LifecyclePhase.MAINTENANCE,
        metadata={"correlation_id": "campaign-signal-test"}),
        execute=surfaces.identify_improvement_signals)

    assert len(evaluation_value.batch.signals) == 1
    signal = evaluation_value.batch.signals[0]
    assert signal.source_kind == "post_adoption_attribution_campaign"
    assert signal.source_digest == result.result_digest
    assert signal.observed_at == result.completed_at
    assert "campaign_digest:" + result.campaign_digest in signal.evidence_refs
    assert "control_id:" + result.control_ids[0] in signal.evidence_refs
    assert "selection_config_digest:" + config_digest in signal.evidence_refs
    assert evaluation_value.receipts[0].disposition == "spec_amendment_candidate"
    assert evaluation_value.amendment_inputs[0]["metadata"]["source_digest"] == result.result_digest
    assert evaluation_value.summary["adoption_performed"] is False
    assert evaluation_value.summary["repository_mutation_performed"] is False
    assert evaluation_value.summary["provider_network_git_operation_performed"] is False
    from sentientos.maintenance_candidate import adapt_governed_signal
    candidate = adapt_governed_signal(signal, base_repository_sha="b05b563895e16bfe614d47e8d22b8cdfb340b6d4")
    assert candidate.confidence == "low"
    assert candidate.source_reference == signal.signal_id
    assert "result_digest:" + result.result_digest in candidate.evidence_references
    assert "source_issuers_unverified" in candidate.declared_constraints
    assert candidate.requested_authority_classes == ("proposal_selection_only",)
    assert selected.verify() == writer.verify()
    assert decision.allowed is True
    reset_runtime_governor()


@pytest.mark.parametrize(("outcomes","expected"), [
    (["target_expectation_satisfied","new_regression_observed"],"protected_regression_observed"),
    (["no_detectable_change"]*2,"no_detectable_target_change"),
    (["target_expectation_satisfied","target_expectation_contradicted"],"heterogeneous_repeated_outcome"),
    (["measurement_failed"]*2,"measurement_failure"),
    (["insufficient_evidence"]*2,"insufficient_target_evidence"),
])
def test_negative_null_mixed_measurement_and_missing_target_are_first_class(tmp_path,outcomes,expected):
    _,_,result=finish(tmp_path,outcomes)
    assert result.classification == expected


def test_missing_control_is_distinct_from_missing_target(tmp_path):
    _,_,result=finish(tmp_path,["missing_control","missing_control"])
    assert result.classification == "insufficient_control_evidence"


def test_interrupted_trial_is_terminal_and_cannot_be_retried_or_omitted(tmp_path):
    owner=MaintenancePostAdoptionAttributionCampaignOwner(tmp_path); p=owner.preregister(protocol())
    owner.record_trial(p,trial_id="trial-1",evaluation=None,controls=(),terminal_status="interrupted",completed_at="2026-01-03T00:00:00Z")
    with pytest.raises(AttributionCampaignError,match="retry_or_replacement"):
        owner.record_trial(p,trial_id="trial-1",evaluation=evaluation(p,0),controls=(control(p,"trial-1"),),terminal_status="completed",completed_at="2026-01-04T00:00:00Z")
    with pytest.raises(AttributionCampaignError,match="incomplete"):
        owner.finalize(p,completed_at="2026-01-05T00:00:00Z")
    owner.record_trial(p,trial_id="trial-2",evaluation=evaluation(p,1),controls=(control(p,"trial-2"),),terminal_status="completed",completed_at="2026-01-05T00:00:00Z")
    assert owner.finalize(p,completed_at="2026-01-06T00:00:00Z").classification == "interrupted_or_invalid_trial"


def test_changed_laws_lineage_retroactivity_and_authority_smuggling_fail_closed(tmp_path):
    owner=MaintenancePostAdoptionAttributionCampaignOwner(tmp_path); p=owner.preregister(protocol())
    with pytest.raises(AttributionCampaignError,match="control_observation_invalid"):
        control(replace(p,controls=(replace(p.controls[0],measurement_law="changed"),)),"trial-1")
    wrong=replace(evaluation(p,0),successor_revision="wrong")
    wrong=replace(wrong,evaluation_digest=digest(wrong.payload()))
    with pytest.raises(AttributionCampaignError,match="lineage"):
        owner.record_trial(p,trial_id="trial-1",evaluation=wrong,controls=(control(p,"trial-1"),),terminal_status="completed",completed_at="2026-01-03T00:00:00Z")
    smuggled=replace(p,authority={**FALSE_AUTHORITY,"git":True})
    with pytest.raises(AttributionCampaignError,match="digest_mismatch"):
        owner.preregister(smuggled)


def test_tamper_fails_reconstruction_and_identity_is_stable(tmp_path):
    _,p,result=finish(tmp_path,["target_expectation_satisfied"]*2)
    assert MaintenancePostAdoptionAttributionCampaignOwner(tmp_path).result(p.campaign_id).result_digest == result.result_digest
    trial_path=next((tmp_path/"trials").glob("*.json")); value=json.loads(trial_path.read_text()); value["outcome"]="indeterminate"; trial_path.write_text(json.dumps(value))
    with pytest.raises(AttributionCampaignError,match="corrupt"):
        MaintenancePostAdoptionAttributionCampaignOwner(tmp_path)


def test_epistemic_and_developmental_adapters_preserve_lineage_without_state_mutation(tmp_path):
    _,_,result=finish(tmp_path,["target_expectation_contradicted"]*2)
    binding=campaign_epistemic_binding(proposition_id="proposition:exact",result=result)
    assert binding.source_artifact_id == result.result_id and binding.dependency_group == result.campaign_digest
    assert binding.evidence_relation == "contradicts" and not hasattr(binding,"state_digest")
    evidence=developmental_evidence_record(result)
    assert evidence["evaluation_ids"] == result.evaluation_ids and evidence["control_ids"] == result.control_ids
    assert evidence["interpretation_performed"] is False


def test_synthetic_cannot_be_mislabeled_as_production(tmp_path):
    _,_,result=finish(tmp_path,["target_expectation_satisfied"]*2)
    assert result.evidence_class == "synthetic" and not result.production_ready
    p=protocol(evidence_class="production")
    with pytest.raises(AttributionCampaignError,match="invalid"):
        control(p,"trial-1",evidence_class="synthetic")
