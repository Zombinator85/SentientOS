from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime

import pytest

from sentientos.avatar_authoring import renderer_handoff
from sentientos.embodied_consequence import (
    ConsequenceStore, EmbodiedConsequenceError, SyntheticIndependentObserver,
    SyntheticRenderer, evaluate_consequence, make_expectation, make_strategy_proposal,
    run_strategy_experiment, world_state_records,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.world_state_board import WorldStateBoardBuilder
from scripts.avatar_authoring import parser as avatar_cli_parser

pytestmark = pytest.mark.no_legacy_skip
T0="2035-01-01T00:00:00+00:00"; T1="2035-01-01T00:00:01+00:00"; T2="2035-01-01T00:00:02+00:00"; TX="2035-01-02T00:00:00+00:00"


def pointer():
    return {"installation_identity":"installation-a","body_identity":"body-a","body_generation":2,
            "artifact_sha256":"sha256:artifact","manifest_digest":"sha256:manifest","pointer_digest":"sha256:pointer"}


def chain(observed_pose="idle"):
    handoff=renderer_handoff(pointer(),renderer_interface_id="renderer:test:v1",requested_pose="wave",requested_expression="neutral",correlation_id="corr-1",commanded_at=T0)
    expectation=make_expectation(installation_body_id="installation-a",body_id="body-a",body_generation=2,
        body_manifest_digest="sha256:manifest",handoff_id=handoff["handoff_id"],handoff_digest=handoff["handoff_digest"],
        renderer_interface_id="renderer:test:v1",requested={"pose":"wave","expression":"neutral"},
        predicted_observables={"pose":"wave"},observable_fields=("pose",),
        comparison_policy={"pose":{"kind":"exact"}},
        expected_observation_source_class="synthetic_independent_fixture",correlation_id="corr-1",
        causal_principal_binding_digest=None,created_at=T0,expires_at=TX)
    report=SyntheticRenderer(applied={"pose":"wave","expression":"neutral"},started_at=T0,completed_at=T1).render_test(handoff)
    observation=SyntheticIndependentObserver(observer_id="separate-observer",observed={"pose":observed_pose,"expression":"neutral"},observed_at=T2).observe(expectation=expectation,handoff=handoff,report=report)
    attribution,comparison=evaluate_consequence(expectation=expectation,handoff=handoff,current_body=pointer(),renderer_report=report,observation=observation,evaluated_at=T2)
    return handoff,expectation,report,observation,attribution,comparison


def test_synthetic_contradiction_projects_and_selects_for_developmental_writeback():
    handoff,expectation,report,observation,attribution,comparison=chain("idle")
    assert attribution["classification"]=="expectation_contradicted"
    assert attribution["renderer_reported_value"]["pose"]=="wave"
    assert attribution["independently_observed_value"]["pose"]=="idle"
    assert attribution["proven_consequence_value"] is None and not attribution["effect_proven"]
    assert attribution["causal_attribution_posture"]=="external_interference_possible"
    assert comparison["counts"]=={"satisfied":0,"contradicted":1,"missing":0,"indeterminate":0}
    records=world_state_records(expectation=expectation,handoff=handoff,renderer_report=report,observation=observation,attribution=attribution,comparison=comparison)
    board=WorldStateBoardBuilder(clock=lambda:datetime.fromisoformat(T2)).build(records)
    target=[f.fact_id for f in board.facts if f.subject.subject_kind in {"embodied_consequence_attribution","embodied_prediction_comparison"}]
    controller=object.__new__(ResidentDevelopmentalWritebackController)
    selected=controller.select_evidence(board,fact_ids=target)
    assert len(selected.facts)==2
    assert all(f["stage"]=="observation" and not f["effect_proven"] for f in selected.facts)


def test_synthetic_satisfied_retains_causal_limit():
    _,_,_,_,attribution,comparison=chain("wave")
    assert attribution["classification"]=="expectation_satisfied"
    assert attribution["causal_attribution_posture"]=="independent_environment_observation"
    assert not attribution["effect_proven"] and attribution["proven_consequence_value"] is None
    assert comparison["counts"]=={"satisfied":1,"contradicted":0,"missing":0,"indeterminate":0}


@pytest.mark.parametrize("mutation,classification",[
    (lambda h,e,r,o: h.update(correlation_id="wrong"),"correlation_mismatch"),
    (lambda h,e,r,o: h.update(body_generation=3),"body_generation_mismatch"),
    (lambda h,e,r,o: h.update(handoff_id="wrong"),"correlation_mismatch"),
    (lambda h,e,r,o: h.update(body_manifest_digest="sha256:wrong"),"correlation_mismatch"),
])
def test_correlation_mismatches_fail_closed(mutation,classification):
    handoff,expectation,report,observation,_,_=chain(); mutation(handoff,expectation,report,observation)
    attribution,_=evaluate_consequence(expectation=expectation,handoff=handoff,current_body=pointer(),renderer_report=report,observation=observation,evaluated_at=T2)
    assert attribution["classification"]==classification


def test_missing_observer_is_renderer_report_only_and_stale_is_indeterminate():
    handoff,expectation,report,_,_,_=chain()
    attribution,comparison=evaluate_consequence(expectation=expectation,handoff=handoff,current_body=pointer(),renderer_report=report,evaluated_at=T2)
    assert attribution["classification"]=="renderer_report_only" and attribution["causal_attribution_posture"]=="renderer_internal_only"
    assert comparison["counts"]["missing"]==1
    stale=replace(expectation,expires_at=T1); stale=replace(stale,expectation_id="",expectation_digest="")
    from sentientos.embodied_consequence import _identity
    eid,dg=_identity("expectation",stale.semantic_payload()); stale=replace(stale,expectation_id=eid,expectation_digest=dg)
    attribution,_=evaluate_consequence(expectation=stale,handoff=handoff,current_body=pointer(),renderer_report=report,evaluated_at=TX)
    assert attribution["classification"]=="indeterminate"


def test_observer_separation_predating_and_synthetic_production_fail_closed():
    handoff,expectation,report,observation,_,_=chain()
    from sentientos.embodied_consequence import make_independent_observation
    with pytest.raises(EmbodiedConsequenceError,match="renderer_cannot"):
        make_independent_observation(**{**observation.semantic_payload(),"observation_source_class":"renderer"})
    early=replace(observation,observed_at="2034-12-31T23:59:59+00:00",observation_id="",observation_digest="")
    from sentientos.embodied_consequence import _identity
    oid,dg=_identity("independent-observation",early.semantic_payload()); early=replace(early,observation_id=oid,observation_digest=dg)
    with pytest.raises(EmbodiedConsequenceError,match="predates"):
        evaluate_consequence(expectation=expectation,handoff=handoff,current_body=pointer(),renderer_report=report,observation=early,evaluated_at=T2)


class CognitiveFixture:
    def __init__(self,consequence_id): self.consequence_id=consequence_id
    def propose(self,*,condition,history,situation):
        has=bool(history)
        return make_strategy_proposal(situation_binding=situation["situation_binding"],body_generation=2,
            relevant_consequence_ids=(self.consequence_id,) if has else (),proposed_next_action_class="observe_then_retry" if has else "retry",
            requested_pose="wave",requested_expression="neutral",retry_prior_strategy=not has,alter_body_or_rig=False,
            more_observation_required=has,distinguishes_renderer_and_observer=has,rationale="fixture history-conditioned proposal" if has else "fixture baseline",
            uncertainty="high",factual_assertions=({"source_id":self.consequence_id,"claim":"contradiction_recorded"},) if has else ())


def test_present_withheld_restored_strategy_experiment_and_external_score():
    *_,attribution,_=chain()
    record={"record_id":"devrec:test","record_digest":"sha256:record","candidate":{"epistemic_posture":"historical_interpretation_not_current_truth"}}
    protocol={"protocol_id":"protocol-1","snapshot_digest":"sha256:snapshot","body_generation":2,"model_id":"deterministic-test-cognition",
        "model_artifact_digest":"sha256:model","inference_budget_digest":"sha256:budget","prompt_schema_digest":"sha256:prompt",
        "renderer_situation_digest":"sha256:situation","software_generation":"test","environment_fixture_digest":"sha256:fixture"}
    result=run_strategy_experiment(protocol=protocol,history_record=record,situation={"situation_binding":"later-wave"},backend=CognitiveFixture(attribution["attribution_id"]),consequence=attribution)
    proposals=result["proposals"]
    assert proposals[0]==proposals[2] and proposals[0]!=proposals[1]
    assert result["scoring"]["outcome"]=="changed" and not result["scoring"]["improvement_claimed"]
    assert result["no_retries"] and not any(result["authority"].values())


def test_restart_reconstruction_and_tamper_detection(tmp_path):
    handoff,expectation,report,observation,attribution,comparison=chain()
    store=ConsequenceStore(tmp_path)
    items=(("expectations",expectation.expectation_id,asdict(expectation),"expectation_digest"),
        ("reports",report.report_id,asdict(report),"report_digest"),("observations",observation.observation_id,asdict(observation),"observation_digest"),
        ("attributions",attribution["attribution_id"],attribution,"attribution_digest"),("comparisons",comparison["comparison_id"],comparison,"comparison_digest"))
    for kind,identity,value,field in items:
        store.put(kind,identity,value); assert ConsequenceStore(tmp_path).get(kind,identity,digest_field=field)==json.loads(json.dumps(value))
    path=store.root/"reports"/f"{report.report_id}.json"; value=json.loads(path.read_text()); value["applied"]["pose"]="idle"; path.write_text(json.dumps(value))
    with pytest.raises(EmbodiedConsequenceError,match="digest_mismatch"): store.get("reports",report.report_id,digest_field="report_digest")


def test_operator_cli_exposes_complete_one_shot_surface():
    choices=avatar_cli_parser()._subparsers._group_actions[0].choices
    assert {"plan-validate","readiness","run-one","candidate-status","adopt","rollback","renderer-handoff","lineage",
            "renderer-report-validate","observation-validate","consequence-evaluate","consequence-show",
            "developmental-assimilate","strategy-experiment"} <= set(choices)
