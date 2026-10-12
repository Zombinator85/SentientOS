from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, replace
from datetime import datetime

import pytest

from sentientos.avatar_authoring import renderer_handoff
from sentientos.embodied_consequence import (
    ConsequenceStore, EmbodiedConsequenceError, SyntheticIndependentObserver,
    SyntheticRenderer, digest, evaluate_consequence, make_expectation, make_strategy_proposal,
    run_strategy_experiment, score_strategy_experiment, world_state_records,
    _history_evidence_scope,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
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


def numeric_chain(*, expected=1, observed=1, comparison_kind="numeric_tolerance",
                  tolerance=0.0, observed_at=T2):
    handoff=renderer_handoff(pointer(),renderer_interface_id="renderer:test:v1",
        requested_pose="wave",requested_expression="neutral",correlation_id="numeric-corr",
        commanded_at=T0)
    expectation=make_expectation(installation_body_id="installation-a",body_id="body-a",
        body_generation=2,body_manifest_digest="sha256:manifest",handoff_id=handoff["handoff_id"],
        handoff_digest=handoff["handoff_digest"],renderer_interface_id="renderer:test:v1",
        requested={"value":expected},predicted_observables={"value":expected},
        observable_fields=("value",),comparison_policy={"value":{"kind":comparison_kind,
        **({"tolerance":tolerance} if comparison_kind=="numeric_tolerance" else {})}},
        expected_observation_source_class="synthetic_independent_fixture",correlation_id="numeric-corr",
        causal_principal_binding_digest=None,created_at=T0,expires_at=TX)
    report=SyntheticRenderer(applied={"value":expected},started_at=T0,completed_at=T1).render_test(handoff)
    observation=SyntheticIndependentObserver(observer_id="numeric-observer",
        observed={"value":observed},observed_at=observed_at).observe(
            expectation=expectation,handoff=handoff,report=report)
    return handoff,expectation,report,observation


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


def test_consequence_records_reach_longitudinal_history_as_historical_evidence(tmp_path):
    handoff,expectation,report,observation,attribution,comparison=chain("idle")
    records=world_state_records(expectation=expectation,handoff=handoff,
        renderer_report=report,observation=observation,attribution=attribution,
        comparison=comparison)
    board=WorldStateBoardBuilder(clock=lambda:datetime.fromisoformat(T2)).build(records)
    assert all(source.finding=="ok" for source in board.sources)

    reconciliation=LongitudinalSelfModelOwner(tmp_path / "self-model").reconcile(
        board,tick_id="consequence-tick")
    attribution_claims=[claim for claim in reconciliation.claims
        if claim.subject_kind=="embodied_consequence_attribution"]
    assert attribution_claims
    lifecycle=next(claim for claim in attribution_claims
        if claim.predicate=="lifecycle.observation.disposition")
    assert lifecycle.claim_category=="historical_interpretation"
    assert lifecycle.status=="historical" and lifecycle.freshness=="unknown"
    lineage=next(claim.value for claim in attribution_claims
        if claim.predicate=="embodiment.prediction_outcome_lineage")
    body_generation=next(claim for claim in attribution_claims
        if claim.predicate=="embodiment.body_generation")
    assert body_generation.claim_category=="historical_interpretation"
    assert body_generation.status=="historical" and body_generation.freshness=="unknown"
    assert lineage["record_id"]==attribution["attribution_id"]
    assert lineage["record_digest"]==attribution["attribution_digest"]
    assert lineage["world_state_source_record_digest"]!=lineage["record_digest"]
    assert lineage["observation_independence_posture"]=="unverified_caller_assertion"
    assert lineage["effect_proven"] is False and lineage["current_truth"] is False


def test_synthetic_satisfied_retains_causal_limit():
    _,_,_,_,attribution,comparison=chain("wave")
    assert attribution["classification"]=="expectation_satisfied"
    assert attribution["causal_attribution_posture"]=="renderer_internal_only"
    assert not attribution["effect_proven"] and attribution["proven_consequence_value"] is None
    assert comparison["counts"]=={"satisfied":1,"contradicted":0,"missing":0,"indeterminate":0}


def test_unissued_measurement_claims_cannot_enter_consequence_lineage():
    handoff,expectation,report,observation,_,_=chain("idle")
    with pytest.raises(EmbodiedConsequenceError,match="measured_evidence_source_unavailable"):
        evaluate_consequence(expectation=expectation,handoff=handoff,current_body=pointer(),
            renderer_report=report,observation=observation,
            measured_evidence=({"measurement":"cpu_percent","value":100,"source":"caller"},),
            evaluated_at=T2)


def test_unresolved_principal_digest_cannot_be_attributed_as_cause():
    handoff,expectation,report,observation,_,_=chain("idle")
    with pytest.raises(EmbodiedConsequenceError,match="causal_principal_source_unavailable"):
        evaluate_consequence(expectation=expectation,handoff=handoff,current_body=pointer(),
            renderer_report=report,observation=observation,
            causal_principal_binding_digest="sha256:"+"a"*64,evaluated_at=T2)


def test_digest_recomputed_comparison_cannot_assert_effect_completion():
    handoff,expectation,report,observation,attribution,comparison=chain("wave")
    from sentientos.embodied_consequence import _identity

    comparison_semantic={k:v for k,v in comparison.items()
        if k not in {"comparison_id","comparison_digest"}}
    comparison_semantic["effect_proven"]=True
    comparison_id,comparison_digest=_identity("prediction-comparison",comparison_semantic)
    forged_comparison={**comparison_semantic,"comparison_id":comparison_id,
        "comparison_digest":comparison_digest}
    attribution_semantic={k:v for k,v in attribution.items()
        if k not in {"attribution_id","attribution_digest"}}
    attribution_semantic["comparison_id"]=comparison_id
    attribution_semantic["comparison_digest"]=comparison_digest
    attribution_id,attribution_digest=_identity("consequence",attribution_semantic)
    rebound_attribution={**attribution_semantic,"attribution_id":attribution_id,
        "attribution_digest":attribution_digest}

    with pytest.raises(EmbodiedConsequenceError,match="consequence_world_state_lineage_invalid"):
        world_state_records(expectation=expectation,handoff=handoff,renderer_report=report,
            observation=observation,attribution=rebound_attribution,comparison=forged_comparison)


def test_consequence_verifier_rejects_digest_recomputed_effect_proof():
    *_,attribution,_=chain("wave")
    from sentientos.embodied_consequence import _identity, _verify_consequence_attribution

    semantic={k:v for k,v in attribution.items()
        if k not in {"attribution_id","attribution_digest"}}
    semantic["effect_proven"]=True
    attribution_id,attribution_digest=_identity("consequence",semantic)
    forged={**semantic,"attribution_id":attribution_id,
        "attribution_digest":attribution_digest}
    with pytest.raises(EmbodiedConsequenceError,match="consequence_attribution_binding_invalid"):
        _verify_consequence_attribution(forged)


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


def test_exact_comparison_does_not_equate_boolean_and_integer():
    handoff,expectation,report,observation=numeric_chain(expected=1,observed=True,
        comparison_kind="exact")
    attribution,comparison=evaluate_consequence(expectation=expectation,handoff=handoff,
        current_body=pointer(),renderer_report=report,observation=observation,evaluated_at=T2)
    assert attribution["classification"]=="expectation_contradicted"
    assert comparison["counts"]["contradicted"]==1


@pytest.mark.parametrize("tolerance",[float("inf"),float("nan"),-1.0])
def test_numeric_tolerance_rejects_nonfinite_or_negative_values(tolerance):
    handoff=renderer_handoff(pointer(),renderer_interface_id="renderer:test:v1",
        requested_pose="wave",requested_expression="neutral",correlation_id="numeric-corr",
        commanded_at=T0)
    with pytest.raises(EmbodiedConsequenceError,match="comparison_tolerance_invalid"):
        make_expectation(installation_body_id="installation-a",body_id="body-a",body_generation=2,
            body_manifest_digest="sha256:manifest",handoff_id=handoff["handoff_id"],
            handoff_digest=handoff["handoff_digest"],renderer_interface_id="renderer:test:v1",
            requested={"value":1},predicted_observables={"value":1},observable_fields=("value",),
            comparison_policy={"value":{"kind":"numeric_tolerance","tolerance":tolerance}},
            expected_observation_source_class="synthetic_independent_fixture",correlation_id="numeric-corr",
            causal_principal_binding_digest=None,created_at=T0,expires_at=TX)


def test_numeric_overflow_and_evaluation_before_observation_remain_indeterminate_or_denied():
    handoff,expectation,report,observation=numeric_chain(expected=1,observed=10**400,tolerance=0.0)
    attribution,comparison=evaluate_consequence(expectation=expectation,handoff=handoff,
        current_body=pointer(),renderer_report=report,observation=observation,evaluated_at=T2)
    assert attribution["classification"]=="indeterminate"
    assert comparison["observable_results"][0]["numeric_range_posture"]=="not_representable_as_finite_float"

    handoff,expectation,report,observation=numeric_chain(observed_at=T2)
    with pytest.raises(EmbodiedConsequenceError,match="comparison_predates_evidence"):
        evaluate_consequence(expectation=expectation,handoff=handoff,current_body=pointer(),
            renderer_report=report,observation=observation,evaluated_at=T1)


class CognitiveFixture:
    def __init__(self,consequence_id): self.consequence_id=consequence_id; self.calls=[]
    def propose(self,*,condition,history,situation):
        self.calls.append(condition)
        has=bool(history)
        return make_strategy_proposal(situation_binding=situation["situation_binding"],body_generation=2,
            relevant_consequence_ids=(self.consequence_id,) if has else (),proposed_next_action_class="observe_then_retry" if has else "retry",
            requested_pose="wave",requested_expression="neutral",retry_prior_strategy=not has,alter_body_or_rig=False,
            more_observation_required=has,distinguishes_renderer_and_observer=has,rationale="fixture history-conditioned proposal" if has else "fixture baseline",
            uncertainty="high",factual_assertions=({"source_id":self.consequence_id,"claim":"contradiction_recorded"},) if has else ())


def test_present_withheld_restored_strategy_experiment_and_external_score(tmp_path):
    *_,attribution,_=chain()
    fact={"fact_id":"fact:causal","source":{"source_id":attribution["attribution_id"],
        "digest":attribution["attribution_digest"],"schema_version":attribution["schema_version"],
        "kind":"embodiment"},"subject":{"subject_id":"body-a",
        "subject_kind":"embodied_consequence_attribution"},"payload":attribution}
    record={"candidate":{"epistemic_posture":"historical_interpretation_not_current_truth",
        "selected_fact_ids":[fact["fact_id"]],"selected_facts":[fact]},
        "created_at":TX,"current_truth":False,"authority":False,"policy":False}
    record["record_digest"]=digest(record)
    record["record_id"]="devrec-"+record["record_digest"][7:31]
    situation={"situation_binding":"later-wave"}
    protocol={"protocol_id":"protocol-1","snapshot_digest":"sha256:snapshot","body_generation":2,"model_id":"deterministic-test-cognition",
        "model_artifact_digest":"sha256:model","inference_budget_digest":"sha256:budget","prompt_schema_digest":"sha256:prompt",
        "renderer_situation_digest":digest(situation),"software_generation":"test","environment_fixture_digest":"sha256:fixture"}
    store=ConsequenceStore(tmp_path)
    backend=CognitiveFixture(attribution["attribution_id"])
    result=run_strategy_experiment(protocol=protocol,history_record=record,situation=situation,
        backend=backend,consequence=attribution,store=store)
    proposals=result["proposals"]
    assert proposals[0]==proposals[2] and proposals[0]!=proposals[1]
    assert result["scoring"]["outcome"]=="changed" and not result["scoring"]["improvement_claimed"]
    assert result["no_retries"] and not any(result["authority"].values())
    assert backend.calls==["history_present","history_withheld","history_restored"]
    recovered_backend=CognitiveFixture(attribution["attribution_id"])
    recovered=run_strategy_experiment(protocol=protocol,history_record=record,situation=situation,
        backend=recovered_backend,consequence=attribution,store=ConsequenceStore(tmp_path))
    assert recovered["experiment_result_id"]==result["experiment_result_id"]
    assert recovered_backend.calls==[]


def test_resource_citation_binds_source_but_never_verifies_claim_semantics():
    *_,attribution,_=chain()
    binding={"lineage_posture":"verified","source_id":"consumption-1",
        "source_digest":"sha256:"+"a"*64}
    def proposal(source_digest):
        return make_strategy_proposal(situation_binding="resource-context",body_generation=2,
            relevant_consequence_ids=(attribution["attribution_id"],),
            proposed_next_action_class="observe",requested_pose="wave",
            requested_expression="neutral",retry_prior_strategy=False,
            alter_body_or_rig=False,more_observation_required=True,
            distinguishes_renderer_and_observer=True,rationale="bounded fixture",
            uncertainty="high",factual_assertions=({"source_id":"consumption-1",
                "source_digest":source_digest,"claim":"measured resource use"},))

    exact=proposal(binding["source_digest"])
    score=score_strategy_experiment(proposals=(exact,exact,exact),consequence=attribution,
        resource_evidence_bindings=(binding,))
    row=score["proposal_scores"][0]
    assert score["outcome"]=="unverified_resource_claims"
    assert row["resource_source_citations"][0]["source_binding_verified"] is True
    assert row["resource_source_citations"][0]["claim_semantics_verified"] is False
    assert row["unverified_resource_factual_assertions"]
    assert score["improvement_claimed"] is False

    substituted=proposal("sha256:"+"b"*64)
    rejected=score_strategy_experiment(proposals=(substituted,substituted,substituted),
        consequence=attribution,resource_evidence_bindings=(binding,))
    assert rejected["outcome"]=="unsupported"
    assert rejected["proposal_scores"][0]["unsupported_factual_assertions"]


def test_model_replacement_resource_history_keeps_invocation_and_cognitive_model_ids_distinct():
    receipt_digests=("consumption-digest",)
    linkage={"effect_receipt_id":"lmrec-invocation","effect_receipt_digest":"invocation-digest",
        "allocation_digest":"allocation-digest","attempt_id":"attempt-1",
        "consumption_receipt_digests":receipt_digests,"model_id":"authority-map-model",
        "model_artifact_digest":"model-artifact-digest"}
    linkage_body={"receipt_digest":linkage["effect_receipt_digest"],
        "allocation_digest":linkage["allocation_digest"],"attempt_id":linkage["attempt_id"],
        "consumption_receipt_digests":receipt_digests}
    payload={"resource_linkage":{**linkage,
        "linkage_digest":hashlib.sha256(json.dumps(linkage_body,sort_keys=True,
            separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()},
        "resource_record":{"source_id":"ledger-record","record_digest":"record-digest",
            "ledger_digest":"ledger-digest"},
        "allocation_identity":{"allocation_digest":"allocation-digest","principal_id":"principal",
            "principal_binding_digest":"principal-binding"},
        "invocation_receipt_id":"lmrec-invocation","invocation_receipt_digest":"invocation-digest",
        "principal_id":"principal","principal_binding_digest":"principal-binding",
        "model_attribution":{"model_id":"cognitive-catalog-model",
            "invocation_model_id":"authority-map-model","model_artifact_digest":"model-artifact-digest",
            "invocation_authority_map_digest":"authority-map-digest"},
        "software_attribution":{"generation":"unknown"},"event_times":[T1],
        "lineage_projection_posture":"complete","lineage_findings":[],
        "model_replacement_run_id":"run-1","model_replacement_run_digest":"run-digest",
        "model_replacement_source_record_id":"source-record",
        "model_replacement_source_record_digest":"source-digest",
        "model_replacement_condition":"model_a_history_present",
        "model_identity_digest":"cognitive-identity-digest",
        "model_provenance_manifest_digest":"provenance-digest",
        "causal_context_id":"context-1","causal_context_digest":"context-digest"}
    fact={"fact_id":"fact:model-replacement-resource",
        "source":{"kind":"resource_governor","source_id":"source-resource",
            "digest":"source-digest"},
        "subject":{"subject_kind":"model_replacement_invocation_resource_lineage"},
        "disposition":"verified","payload":payload}
    record={"candidate":{"selected_fact_ids":[fact["fact_id"]],"selected_facts":[fact]}}

    accepted=_history_evidence_scope(record)
    assert accepted["posture"]=="resource_invocation_lineage_history"
    binding=accepted["resource_bindings"][0]
    assert binding["cognitive_model_id"]=="cognitive-catalog-model"
    assert binding["invocation_model_id"]=="authority-map-model"

    legacy_fact=json.loads(json.dumps(fact))
    legacy_fact["subject"]["subject_kind"]="strategy_invocation_resource_lineage"
    legacy_model=legacy_fact["payload"]["model_attribution"]
    legacy_model["model_id"]="authority-map-model"
    legacy_model.pop("invocation_model_id")
    legacy_record={"candidate":{"selected_fact_ids":[legacy_fact["fact_id"]],
        "selected_facts":[legacy_fact]}}
    assert _history_evidence_scope(legacy_record)["posture"]=="resource_invocation_lineage_history"

    payload["model_attribution"]["invocation_model_id"]="substituted-model"
    rejected=_history_evidence_scope(record)
    assert rejected["posture"]=="resource_evidence_lineage_incomplete"


def test_conflicting_resource_source_digests_are_rejected():
    *_,attribution,_=chain()
    proposal=make_strategy_proposal(situation_binding="resource-context",body_generation=2,
        relevant_consequence_ids=(attribution["attribution_id"],),
        proposed_next_action_class="observe",requested_pose="wave",
        requested_expression="neutral",retry_prior_strategy=False,
        alter_body_or_rig=False,more_observation_required=True,
        distinguishes_renderer_and_observer=True,rationale="bounded fixture",
        uncertainty="high",factual_assertions=())
    with pytest.raises(EmbodiedConsequenceError,match="resource_source_identity_conflict"):
        score_strategy_experiment(proposals=(proposal,proposal,proposal),consequence=attribution,
            resource_evidence_bindings=(
                {"lineage_posture":"verified","source_id":"consumption-1","source_digest":"sha256:"+"a"*64},
                {"lineage_posture":"verified","source_id":"consumption-1","source_digest":"sha256:"+"b"*64},
            ))


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
