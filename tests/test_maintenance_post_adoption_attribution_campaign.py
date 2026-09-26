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


def protocol(*, evidence_class="synthetic"):
    return make_campaign_protocol(maintenance_task_id="task-1", proposal_id="proposal-1", signal_ids=("signal-1",),
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


def finish(tmp_path, outcomes, *, matches=None, evidence_class="synthetic"):
    owner=MaintenancePostAdoptionAttributionCampaignOwner(tmp_path); p=owner.preregister(protocol(evidence_class=evidence_class))
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
