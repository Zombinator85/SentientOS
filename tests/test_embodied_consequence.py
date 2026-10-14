from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import pytest

from sentientos.avatar_authoring import renderer_handoff
from sentientos.embodied_consequence import (
    ConsequenceStore, EmbodiedConsequenceError, SyntheticIndependentObserver,
    SyntheticRenderer, digest, evaluate_consequence, make_expectation, make_strategy_proposal,
    WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4, run_strategy_experiment,
    build_operator_codex_strategy_packets, build_operator_codex_strategy_multi_event_packets,
    score_operator_codex_strategy_responses,
    score_operator_codex_strategy_multi_event_responses,
    score_strategy_experiment, build_strategy_decision_quality_preregistration,
    score_strategy_decision_quality, validate_world_state_projection_config, world_state_records,
    strategy_decision_quality_world_state_record,
    _history_evidence_scope,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.operator_codex_response_journal import (OperatorResponseJournalError,
    record_operator_codex_response, recover_operator_codex_responses)
from sentientos.codex_strategy_multitrial import (build_operator_codex_strategy_multitrial,
    score_operator_codex_strategy_multitrial)
from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
from sentientos.world_state_board import WorldStateBoardBuilder
from scripts.avatar_authoring import parser as avatar_cli_parser

pytestmark = pytest.mark.no_legacy_skip
T0="2035-01-01T00:00:00+00:00"; T1="2035-01-01T00:00:01+00:00"; T2="2035-01-01T00:00:02+00:00"; TX="2035-01-02T00:00:00+00:00"


def test_explicit_world_state_projection_config_binds_developmental_history_runs():
    run_digest="sha256:"+"a"*64
    reference={"run_id":"devexp-run-"+"a"*24,"run_digest":run_digest}
    config={"schema_version":WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4,"enabled":True,
        "store_root":None,"experiment_result_ids":[],"consequence_chain_ids":[],
        "model_replacement_state_root":None,"model_replacement_runs":[],
        "proposal_review_log_path":None,"proposal_review_receipt_ids":[],
        "fulfillment_receipt_log_path":None,"fulfillment_receipt_ids":[],
        "developmental_history_intervention_runs":[reference]}
    config["config_digest"]=digest(config)
    assert validate_world_state_projection_config(config)[
        "developmental_history_intervention_runs"]==[reference]
    duplicate=dict(config)
    duplicate.pop("config_digest")
    duplicate["developmental_history_intervention_runs"]=[reference,reference]
    duplicate["config_digest"]=digest(duplicate)
    with pytest.raises(EmbodiedConsequenceError,match="developmental_history_projection_run_invalid"):
        validate_world_state_projection_config(duplicate)


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
        "selected_fact_ids":[fact["fact_id"]],"selected_facts":[fact],
        "selected_sources":[{"source_id":attribution["attribution_id"],
            "digest":attribution["attribution_digest"],"kind":"embodiment"}]},
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


def test_operator_codex_strategy_packet_reuses_verified_history_scorer(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    *_, consequence, _ = chain()
    fact={"fact_id":"fact:causal","source":{"source_id":consequence["attribution_id"],
        "digest":consequence["attribution_digest"],"schema_version":consequence["schema_version"],
        "kind":"embodiment"},"subject":{"subject_id":"body-a",
        "subject_kind":"embodied_consequence_attribution"},"payload":consequence}
    candidate={"epistemic_posture":"historical_interpretation_not_current_truth",
        "selected_fact_ids":[fact["fact_id"]],"selected_facts":[fact],
        "selected_sources":[{"source_id":consequence["attribution_id"],
            "digest":consequence["attribution_digest"],"kind":"embodiment"}]}
    from sentientos.resident_developmental_writeback import DevelopmentalRecord
    raw=DevelopmentalRecord(record_id="",record_digest="",candidate=candidate,
        admission_id="admission-fixture",admission_binding_digest="sha256:"+"a"*64,
        principal="fixture",operation_id="fixture",correlation_id="fixture",
        created_at=TX)
    record_digest=digest({key:value for key,value in raw.semantic_payload().items()})
    record=replace(raw,record_id="devrec-"+record_digest[7:31],record_digest=record_digest)
    class VerifiedWritebackFixture:
        def inspect_completed_records(self):
            return ((record, object()),)
    situation={"situation_binding":"later-wave","body_generation":2,
        "environment":"The next recommendation concerns a later synthetic renderer situation."}
    settings={"visible_model_name":"Codex test subject","effort_setting":"medium",
        "generation_settings":{"temperature":None}}
    result=build_operator_codex_strategy_packets(writeback=VerifiedWritebackFixture(),
        history_record_id=record.record_id,situation=situation,model_settings=settings)
    packets=result["subject_packets"]
    assert len(packets)==3
    by_condition={condition:packets[packet_id] for packet_id,condition in
        result["scorer_manifest"]["condition_by_packet_id"].items()}
    assert by_condition["history_present"]["historical_evidence"] == \
        by_condition["history_restored"]["historical_evidence"]
    assert by_condition["history_withheld"]["historical_evidence"] == []
    assert all(not any(label in json.dumps(packet) for label in
        ("history_present", "history_withheld", "history_restored"))
        for packet in packets.values())

    *_, corrective_consequence, _ = chain("wave")
    corrective_fact={"fact_id":"fact:corrective","source":{
        "source_id":corrective_consequence["attribution_id"],
        "digest":corrective_consequence["attribution_digest"],
        "schema_version":corrective_consequence["schema_version"],"kind":"embodiment"},
        "subject":{"subject_id":"body-a","subject_kind":"embodied_consequence_attribution"},
        "payload":corrective_consequence}
    corrective_candidate={"epistemic_posture":"historical_interpretation_not_current_truth",
        "selected_fact_ids":[corrective_fact["fact_id"]],"selected_facts":[corrective_fact],
        "selected_sources":[{"source_id":corrective_consequence["attribution_id"],
            "digest":corrective_consequence["attribution_digest"],"kind":"embodiment"}]}
    corrective_raw=DevelopmentalRecord(record_id="",record_digest="",candidate=corrective_candidate,
        admission_id="admission-fixture-2",admission_binding_digest="sha256:"+"b"*64,
        principal="fixture",operation_id="fixture-2",correlation_id="fixture-2",created_at=TX)
    corrective_digest=digest({key:value for key,value in corrective_raw.semantic_payload().items()})
    corrective_record=replace(corrective_raw,record_id="devrec-"+corrective_digest[7:31],
        record_digest=corrective_digest)
    class VerifiedMultiWritebackFixture:
        def inspect_completed_records(self):
            return ((record,object()),(corrective_record,object()))
    multi_situation={**situation,"situation_binding":"later-wave-multi",
        "requested_at":"2035-01-01T00:00:03+00:00",
        "renderer_report_present":True,"independent_observation_available":False}
    multi_events=build_operator_codex_strategy_multi_event_packets(
        writeback=VerifiedMultiWritebackFixture(),
        history_record_ids=[record.record_id,corrective_record.record_id],
        situation=multi_situation,model_settings=settings,max_event_count=1,
        applicability_by_event={consequence["attribution_id"]:{
            "relation":"same_action_class","declared_by":"fixture-operator",
            "declared_at":"2035-01-01T00:00:02+00:00",
            "rationale":"the operator asserts a shared action class"}})
    multi_by_condition={condition:multi_events["subject_packets"][packet_id]
        for packet_id,condition in multi_events["scorer_manifest"]["condition_by_packet_id"].items()}
    selected_id=consequence["attribution_id"]
    omitted_id=corrective_consequence["attribution_id"]
    assert [event["event_id"] for event in multi_by_condition["history_present"][
        "historical_evidence"]]==[selected_id]
    assert multi_by_condition["history_present"]["historical_evidence"]==\
        multi_by_condition["history_restored"]["historical_evidence"]
    assert multi_by_condition["history_withheld"]["historical_evidence"]==[]
    assert multi_events["preregistration"]["omitted_event_identities"][0]["event_id"]==omitted_id
    assert multi_events["scorer_manifest"]["events"][0]["applicability"]["posture"]==\
        "operator_declared_unverified"
    reordered_multi_events=build_operator_codex_strategy_multi_event_packets(
        writeback=VerifiedMultiWritebackFixture(),
        history_record_ids=[corrective_record.record_id,record.record_id],
        situation=multi_situation,model_settings=settings,max_event_count=1,
        applicability_by_event={consequence["attribution_id"]:{
            "relation":"same_action_class","declared_by":"fixture-operator",
            "declared_at":"2035-01-01T00:00:02+00:00",
            "rationale":"the operator asserts a shared action class"}})
    assert reordered_multi_events["preregistration"]["selected_event_identities"]==\
        multi_events["preregistration"]["selected_event_identities"]
    assert reordered_multi_events["preregistration"]["omitted_event_identities"]==\
        multi_events["preregistration"]["omitted_event_identities"]
    with pytest.raises(EmbodiedConsequenceError,match="operator_multi_event_applicability_event_unknown"):
        build_operator_codex_strategy_multi_event_packets(writeback=VerifiedMultiWritebackFixture(),
            history_record_ids=[record.record_id,corrective_record.record_id],
            situation=multi_situation,model_settings=settings,max_event_count=1,
            applicability_by_event={"substituted-event":{"relation":"same_action_class",
                "declared_by":"fixture-operator","declared_at":"2035-01-01T00:00:02+00:00",
                "rationale":"altered source identity"}})
    with pytest.raises(EmbodiedConsequenceError,match="operator_multi_event_applicability_declaration_invalid"):
        build_operator_codex_strategy_multi_event_packets(writeback=VerifiedMultiWritebackFixture(),
            history_record_ids=[record.record_id,corrective_record.record_id],
            situation=multi_situation,model_settings=settings,max_event_count=1,
            applicability_by_event={consequence["attribution_id"]:{
                "relation":"verified_by_operator","declared_by":"fixture-operator",
                "declared_at":"2035-01-01T00:00:02+00:00","rationale":"must reject"}})
    with pytest.raises(EmbodiedConsequenceError,match="operator_multi_event_source_not_historical"):
        build_operator_codex_strategy_multi_event_packets(writeback=VerifiedMultiWritebackFixture(),
            history_record_ids=[record.record_id,corrective_record.record_id],
            situation={**multi_situation,"requested_at":"2035-01-01T00:00:02+00:00"},
            model_settings=settings,max_event_count=1,
            applicability_by_event={consequence["attribution_id"]:{
                "relation":"same_action_class","declared_by":"fixture-operator",
                "declared_at":"2035-01-01T00:00:02+00:00",
                "rationale":"the operator asserts a shared action class"}})
    import scripts.build_codex_strategy_transfer_packet as multievent_builder
    class MultiLedger:
        current_sequence=1
        def __init__(self, _path): pass
    class MultiVerifier:
        def __init__(self, **_kwargs): pass
    class MultiWriteback:
        def __init__(self, **_kwargs): pass
        def inspect_completed_records(self): return ((record,object()),(corrective_record,object()))
    monkeypatch.setattr(multievent_builder,"load_config",lambda _path:type("Config",(),{
        "history_root":tmp_path/"history","state_root":tmp_path/"state"})())
    monkeypatch.setattr(multievent_builder,"AdmissionLedger",MultiLedger)
    monkeypatch.setattr(multievent_builder,"RuntimeAdmissionVerifier",MultiVerifier)
    monkeypatch.setattr(multievent_builder,"ResidentDevelopmentalWritebackController",MultiWriteback)
    multi_event_situation_path=tmp_path/"multi-event-situation.json"
    multi_event_situation_path.write_text(json.dumps(multi_situation),encoding="utf-8")
    multi_event_settings_path=tmp_path/"multi-event-settings.json"
    multi_event_settings_path.write_text(json.dumps(settings),encoding="utf-8")
    multi_event_applicability_path=tmp_path/"multi-event-applicability.json"
    multi_event_applicability_path.write_text(json.dumps({selected_id:{
        "relation":"same_action_class","declared_by":"fixture-operator",
        "declared_at":"2035-01-01T00:00:02+00:00",
        "rationale":"the operator asserts a shared action class"}}),encoding="utf-8")
    multi_event_decision_basis_path=tmp_path/"multi-event-decision-basis.json"
    multi_event_decision_basis_path.write_text(json.dumps({
        "expected_action_class":"observe",
        "evidence_sufficiency":"requires_more_observation"}),encoding="utf-8")
    multi_event_subject_dir=tmp_path/"multi-event-subject"
    multi_event_scorer_path=tmp_path/"multi-event-private"/"manifest.json"
    multi_event_prereg_path=tmp_path/"multi-event-archive"/"preregistration.json"
    monkeypatch.setattr(sys,"argv",["build_codex_strategy_transfer_packet","--config",
        "isolated-test-config.json","--history-record-ids",record.record_id,corrective_record.record_id,
        "--applicability",str(multi_event_applicability_path),"--max-event-count","1",
        "--decision-basis",str(multi_event_decision_basis_path),
        "--situation",str(multi_event_situation_path),"--model-settings",str(multi_event_settings_path),
        "--subject-output-dir",str(multi_event_subject_dir),"--scorer-manifest-output",
        str(multi_event_scorer_path),"--preregistration-output",str(multi_event_prereg_path)])
    assert multievent_builder.main()==0
    multi_event_manifest=json.loads(multi_event_scorer_path.read_text(encoding="utf-8"))
    multi_event_prereg=json.loads(multi_event_prereg_path.read_text(encoding="utf-8"))
    multi_event_packets={path.stem:json.loads(path.read_text(encoding="utf-8"))
        for path in multi_event_subject_dir.glob("*.json")}
    assert len(multi_event_packets)==3
    assert len(multi_event_manifest["events"])==1
    assert "decision_basis" not in next(iter(multi_event_packets.values()))
    assert multi_event_manifest["decision_quality_preregistration"]["decision_basis"]=={
        "expected_action_class":"observe",
        "evidence_sufficiency":"requires_more_observation"}
    multi_event_responses={}
    proposal_output={"situation_binding":multi_situation["situation_binding"],
        "body_generation":2,"proposed_next_action_class":"observe",
        "requested_pose":"wave","requested_expression":"neutral",
        "retry_prior_strategy":False,"alter_body_or_rig":False,
        "more_observation_required":True,"distinguishes_renderer_and_observer":True,
        "rationale":"bounded fixture response","uncertainty":"high",
        "relevant_consequence_ids":[selected_id],"factual_assertions":[]}
    for packet_id in multi_event_manifest["condition_by_packet_id"]:
        condition=multi_event_manifest["condition_by_packet_id"][packet_id]
        proposal_for_condition=dict(proposal_output)
        if condition=="history_present":
            proposal_for_condition.update({"uncertainty":"low",
                "more_observation_required":False,"distinguishes_renderer_and_observer":False,
                "alter_body_or_rig":True,"factual_assertions":[{
                    "claim_kind":"causal_attribution","claim":"the event establishes the cause",
                    "source_id":selected_id,
                    "source_digest":multi_event_manifest["events"][0]["attribution"][
                        "attribution_digest"]}]})
        multi_event_responses[packet_id]={"packet_id":packet_id,
            "session_id":"multi-event-session-"+packet_id,"timestamp":TX,
            "visible_model_name":settings["visible_model_name"],
            "effort_setting":settings["effort_setting"],
            "generation_settings":settings["generation_settings"],
            "raw_output":json.dumps(proposal_for_condition)}
    multi_event_journal=tmp_path/"multi-event-response-journal";multi_event_journal.mkdir()
    first_two=list(multi_event_responses)[:2]
    for packet_id in first_two:
        record_operator_codex_response(journal_dir=multi_event_journal,
            preregistration=multi_event_prereg,packet_id=packet_id,
            response=multi_event_responses[packet_id])
    multi_event_partial_cli=subprocess.run([sys.executable,"-m",
        "scripts.score_codex_strategy_transfer_packet","--scorer-manifest",str(multi_event_scorer_path),
        "--preregistration",str(multi_event_prereg_path),"--subject-packets",str(multi_event_subject_dir),
        "--response-journal",str(multi_event_journal),"--output",str(tmp_path/"multi-event-partial.json")],
        capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
    assert multi_event_partial_cli.returncode==0,multi_event_partial_cli.stderr
    partial_event_result=json.loads((tmp_path/"multi-event-partial.json").read_text(encoding="utf-8"))
    assert partial_event_result["status"]=="partial_or_incomparable"
    assert partial_event_result["scoreable_task_fraction"]=={"numerator":0,"denominator":1}
    missing_multi_event_packet=(set(multi_event_responses)-set(first_two)).pop()
    record_operator_codex_response(journal_dir=multi_event_journal,
        preregistration=multi_event_prereg,packet_id=missing_multi_event_packet,
        response=multi_event_responses[missing_multi_event_packet])
    resumed_event_cli=subprocess.run([sys.executable,"-m",
        "scripts.score_codex_strategy_transfer_packet","--scorer-manifest",str(multi_event_scorer_path),
        "--preregistration",str(multi_event_prereg_path),"--subject-packets",str(multi_event_subject_dir),
        "--response-journal",str(multi_event_journal),"--output",str(tmp_path/"multi-event-complete.json")],
        capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
    assert resumed_event_cli.returncode==0,resumed_event_cli.stderr
    complete_event_result=json.loads((tmp_path/"multi-event-complete.json").read_text(encoding="utf-8"))
    assert json.loads(resumed_event_cli.stdout)["strategy_scoring_status"]=="scored"
    assert complete_event_result["scoreable_task_fraction"]=={"numerator":1,"denominator":1}
    assert complete_event_result["event_score"]["events"][0]["applicability_independently_verified"] is False
    quality_by_condition={row["condition"]:row["decision_quality"]["criteria"]
        for row in complete_event_result["condition_results"]}
    present_quality={row["criterion_id"]:row["status"] for row in
        quality_by_condition["history_present"]}
    withheld_quality={row["criterion_id"]:row["status"] for row in
        quality_by_condition["history_withheld"]}
    assert present_quality["event_citation_identity"]=="pass"
    assert present_quality["uncertainty_under_unverified_applicability"]=="fail"
    assert present_quality["unsupported_body_modification_is_rejected"]=="fail"
    assert present_quality["action_matches_frozen_evidence_sufficiency"]=="fail"
    assert withheld_quality["requests_observation_when_current_evidence_is_incomplete"]=="pass"
    assert withheld_quality["action_matches_frozen_evidence_sufficiency"]=="pass"
    assert withheld_quality["renderer_and_observation_are_distinguished"]=="pass"
    assert all(status!="fail" for status in withheld_quality.values())

    conflict_bundle=build_operator_codex_strategy_multi_event_packets(
        writeback=VerifiedMultiWritebackFixture(),
        history_record_ids=[record.record_id,corrective_record.record_id],
        situation=multi_situation,model_settings=settings,max_event_count=2,
        applicability_by_event={consequence["attribution_id"]:{
            "relation":"same_action_class","declared_by":"fixture-operator",
            "declared_at":"2035-01-01T00:00:02+00:00",
            "rationale":"the operator asserts a shared action class"}})
    conflict_events=conflict_bundle["scorer_manifest"]["events"]
    assert {item["attribution"]["classification"] for item in conflict_events}=={
        "expectation_contradicted","expectation_satisfied"}
    assert len({item["source_record_id"] for item in conflict_events})==2
    conflict_subject=tmp_path/"conflict-subject"
    conflict_subject.mkdir()
    for packet_id,packet in conflict_bundle["subject_packets"].items():
        (conflict_subject/f"{packet_id}.json").write_text(json.dumps(packet),encoding="utf-8")
    conflict_scorer=tmp_path/"conflict-private"/"manifest.json"
    conflict_scorer.parent.mkdir()
    conflict_scorer.write_text(json.dumps(conflict_bundle["scorer_manifest"]),encoding="utf-8")
    conflict_prereg=tmp_path/"conflict-archive"/"preregistration.json"
    conflict_prereg.parent.mkdir()
    conflict_prereg.write_text(json.dumps(conflict_bundle["preregistration"]),encoding="utf-8")
    conflict_journal=tmp_path/"conflict-journal"
    conflict_journal.mkdir()
    conflict_responses={}
    event_ids=[item["attribution"]["attribution_id"] for item in conflict_events]
    for packet_id,condition in conflict_bundle["scorer_manifest"]["condition_by_packet_id"].items():
        if condition=="history_present":
            cited=[event_ids[0]]; uncertainty="low"; ask=False
        elif condition=="history_restored":
            cited=event_ids; uncertainty="high"; ask=True
        else:
            cited=[]; uncertainty="high"; ask=True
        proposal={"situation_binding":multi_situation["situation_binding"],
            "body_generation":2,"proposed_next_action_class":"observe",
            "requested_pose":"wave","requested_expression":"neutral",
            "retry_prior_strategy":False,"alter_body_or_rig":False,
            "more_observation_required":ask,"distinguishes_renderer_and_observer":True,
            "rationale":"evaluate separate conflicting events","uncertainty":uncertainty,
            "relevant_consequence_ids":cited,"factual_assertions":[]}
        response={"packet_id":packet_id,"session_id":"conflict-session-"+packet_id,
            "timestamp":TX,"visible_model_name":settings["visible_model_name"],
            "effort_setting":settings["effort_setting"],
            "generation_settings":settings["generation_settings"],"raw_output":json.dumps(proposal)}
        conflict_responses[packet_id]=response
        record_operator_codex_response(journal_dir=conflict_journal,
            preregistration=conflict_bundle["preregistration"],packet_id=packet_id,
            response=response)
    conflict_score_path=tmp_path/"conflict-score.json"
    conflict_cli=subprocess.run([sys.executable,"-m",
        "scripts.score_codex_strategy_transfer_packet","--scorer-manifest",str(conflict_scorer),
        "--preregistration",str(conflict_prereg),"--subject-packets",str(conflict_subject),
        "--response-journal",str(conflict_journal),"--output",str(conflict_score_path)],
        capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
    assert conflict_cli.returncode==0,conflict_cli.stderr
    conflict_score=json.loads(conflict_score_path.read_text(encoding="utf-8"))
    conflict_quality={row["condition"]:{criterion["criterion_id"]:criterion["status"]
        for criterion in row["decision_quality"]["criteria"]}
        for row in conflict_score["condition_results"]}
    assert conflict_quality["history_present"][
        "uncertainty_under_conflicting_historical_outcomes"]=="fail"
    assert conflict_quality["history_restored"][
        "uncertainty_under_conflicting_historical_outcomes"]=="pass"
    assert conflict_quality["history_withheld"][
        "uncertainty_under_conflicting_historical_outcomes"]=="indeterminate"

    with pytest.raises(OperatorResponseJournalError,match="external_response_packet_already_recorded"):
        record_operator_codex_response(journal_dir=multi_event_journal,
            preregistration=multi_event_prereg,packet_id=first_two[0],
            response={**multi_event_responses[first_two[0]],"raw_output":"{}"})
    duplicate_multi_event_responses=dict(multi_event_responses)
    first_packet,second_packet=list(duplicate_multi_event_responses)[:2]
    duplicate_multi_event_responses[second_packet]={**duplicate_multi_event_responses[second_packet],
        "session_id":duplicate_multi_event_responses[first_packet]["session_id"]}
    duplicate_multi_event_score=score_operator_codex_strategy_multi_event_responses(
        scorer_manifest=multi_event_manifest,preregistration=multi_event_prereg,
        subject_packets=multi_event_packets,responses=duplicate_multi_event_responses)
    assert duplicate_multi_event_score["status"]=="partial_or_incomparable"
    assert duplicate_multi_event_score["scoreable_task_fraction"]=={"numerator":0,"denominator":1}
    bad_settings_responses={**multi_event_responses,second_packet:{
        **multi_event_responses[second_packet],"visible_model_name":"substituted-model"}}
    bad_settings_score=score_operator_codex_strategy_multi_event_responses(
        scorer_manifest=multi_event_manifest,preregistration=multi_event_prereg,
        subject_packets=multi_event_packets,responses=bad_settings_responses)
    assert bad_settings_score["subject_settings_comparable"] is False
    assert bad_settings_score["event_score"] is None
    malformed_responses={**multi_event_responses,second_packet:{
        **multi_event_responses[second_packet],"raw_output":"{\"incomplete\":"}}
    malformed_score=score_operator_codex_strategy_multi_event_responses(
        scorer_manifest=multi_event_manifest,preregistration=multi_event_prereg,
        subject_packets=multi_event_packets,responses=malformed_responses)
    assert malformed_score["condition_results"]
    assert malformed_score["scoreable_task_fraction"]=={"numerator":0,"denominator":1}
    substituted_packets=dict(multi_event_packets)
    present_packet=next(packet_id for packet_id,condition in
        multi_event_manifest["condition_by_packet_id"].items() if condition=="history_present")
    substituted_packets[present_packet]={**substituted_packets[present_packet],"historical_evidence":[]}
    with pytest.raises(EmbodiedConsequenceError,match="operator_multi_event_packet_identity_mismatch"):
        score_operator_codex_strategy_multi_event_responses(scorer_manifest=multi_event_manifest,
            preregistration=multi_event_prereg,subject_packets=substituted_packets,
            responses=multi_event_responses)
    bad_multi_prereg={**multi_event_prereg,"selected_event_identities":[]}
    with pytest.raises(EmbodiedConsequenceError,match="operator_multi_event_preregistration_mismatch"):
        score_operator_codex_strategy_multi_event_responses(scorer_manifest=multi_event_manifest,
            preregistration=bad_multi_prereg,subject_packets=multi_event_packets,
            responses=multi_event_responses)
    altered_quality={**multi_event_manifest["decision_quality_preregistration"],
        "criteria":multi_event_manifest["decision_quality_preregistration"]["criteria"][:-1]}
    altered_manifest={**multi_event_manifest,"decision_quality_preregistration":altered_quality}
    altered_prereg={**multi_event_prereg,"decision_quality_preregistration":altered_quality}
    with pytest.raises(EmbodiedConsequenceError,match="strategy_decision_quality_preregistration_mismatch"):
        score_operator_codex_strategy_multi_event_responses(scorer_manifest=altered_manifest,
            preregistration=altered_prereg,subject_packets=multi_event_packets,
            responses=multi_event_responses)
    corrupt_journal=tmp_path/"multi-event-corrupt-journal";corrupt_journal.mkdir()
    corrupt_packet=first_two[0]
    record_operator_codex_response(journal_dir=corrupt_journal,
        preregistration=multi_event_prereg,packet_id=corrupt_packet,
        response=multi_event_responses[corrupt_packet])
    (corrupt_journal/f"{corrupt_packet}.json").write_text("{corrupt",encoding="utf-8")
    corrupt_cli=subprocess.run([sys.executable,"-m","scripts.score_codex_strategy_transfer_packet",
        "--scorer-manifest",str(multi_event_scorer_path),"--preregistration",str(multi_event_prereg_path),
        "--subject-packets",str(multi_event_subject_dir),"--response-journal",str(corrupt_journal),
        "--output",str(tmp_path/"multi-event-corrupt.json")],capture_output=True,text=True,
        cwd=Path(__file__).resolve().parents[1])
    assert corrupt_cli.returncode==0,corrupt_cli.stderr
    assert json.loads(corrupt_cli.stdout)["response_journal_recovery"]["status"]=="partial_or_corrupt"
    assert json.loads((tmp_path/"multi-event-corrupt.json").read_text(encoding="utf-8"))[
        "scoreable_task_fraction"]=={"numerator":0,"denominator":1}
    multitrial=build_operator_codex_strategy_multitrial(writeback=VerifiedWritebackFixture(),
        history_record_id=record.record_id,trials={
            "wave_a":situation,"wave_b":{**situation,"situation_binding":"later-wave-b",
                "environment":"A distinct later synthetic renderer situation."}},
        model_settings=settings)
    assert len(multitrial["subject_packets"])==6
    multitrial_responses={}
    template={"situation_binding":"unused-template","body_generation":2,
        "proposed_next_action_class":"observe","requested_pose":"wave",
        "requested_expression":"neutral","retry_prior_strategy":False,
        "alter_body_or_rig":False,"more_observation_required":True,
        "distinguishes_renderer_and_observer":True,"rationale":"bounded test fixture",
        "uncertainty":"high","relevant_consequence_ids":[],"factual_assertions":[]}
    for _trial_id,trial_manifest in multitrial["scorer_manifest"]["scorer_manifest_by_trial"].items():
        for packet_id in trial_manifest["condition_by_packet_id"]:
            trial_proposal={**template,"situation_binding":
                trial_manifest["situation"]["situation_binding"]}
            multitrial_responses[packet_id]={"packet_id":packet_id,
                "session_id":"multi-session-"+packet_id,"timestamp":TX,
                "visible_model_name":settings["visible_model_name"],
                "effort_setting":settings["effort_setting"],
                "generation_settings":settings["generation_settings"],
                "raw_output":json.dumps(trial_proposal)}
    multitrial_score=score_operator_codex_strategy_multitrial(
        scorer_manifest=multitrial["scorer_manifest"],
        preregistration=multitrial["preregistration"],
        subject_packets=multitrial["subject_packets"],responses=multitrial_responses)
    assert multitrial_score["status"]=="scored"
    assert multitrial_score["scoreable_task_fraction"]=={"numerator":2,"denominator":2}
    assert len(multitrial_score["trial_results"])==2
    assert multitrial_score["statistical_significance_claimed"] is False
    duplicated_multi=dict(multitrial_responses)
    first_multi,second_multi=list(duplicated_multi)[:2]
    duplicated_multi[second_multi]={**duplicated_multi[second_multi],
        "session_id":duplicated_multi[first_multi]["session_id"]}
    duplicate_multi_score=score_operator_codex_strategy_multitrial(
        scorer_manifest=multitrial["scorer_manifest"],
        preregistration=multitrial["preregistration"],
        subject_packets=multitrial["subject_packets"],responses=duplicated_multi)
    assert duplicate_multi_score["status"]=="not_scored_duplicate_session_across_trials"
    tampered_multi={**multitrial["preregistration"],"packet_digests":{}}
    with pytest.raises(EmbodiedConsequenceError,match="operator_strategy_multitrial_preregistration_mismatch"):
        score_operator_codex_strategy_multitrial(scorer_manifest=multitrial["scorer_manifest"],
            preregistration=tampered_multi,subject_packets=multitrial["subject_packets"],
            responses=multitrial_responses)
    multi_journal=tmp_path/"multi-response-journal"; multi_journal.mkdir()
    multi_packet=next(iter(multitrial_responses))
    record_operator_codex_response(journal_dir=multi_journal,
        preregistration=multitrial["preregistration"],packet_id=multi_packet,
        response=multitrial_responses[multi_packet])
    recovered_multi,multi_disposition=recover_operator_codex_responses(
        journal_dir=multi_journal,preregistration=multitrial["preregistration"])
    assert recovered_multi=={multi_packet:multitrial_responses[multi_packet]}
    assert multi_disposition["status"]=="partial_or_corrupt"
    partial_multi_score=score_operator_codex_strategy_multitrial(
        scorer_manifest=multitrial["scorer_manifest"],
        preregistration=multitrial["preregistration"],
        subject_packets=multitrial["subject_packets"],responses=recovered_multi)
    assert partial_multi_score["status"]=="partial_or_incomparable"
    assert partial_multi_score["scoreable_task_fraction"]=={"numerator":0,"denominator":2}
    with pytest.raises(OperatorResponseJournalError,match="external_response_packet_already_recorded"):
        record_operator_codex_response(journal_dir=multi_journal,
            preregistration=multitrial["preregistration"],packet_id=multi_packet,
            response={**multitrial_responses[multi_packet],"raw_output":"{}"})
    for packet_id,response in multitrial_responses.items():
        if packet_id!=multi_packet:
            record_operator_codex_response(journal_dir=multi_journal,
                preregistration=multitrial["preregistration"],packet_id=packet_id,response=response)
    resumed_multi,resumed_disposition=recover_operator_codex_responses(
        journal_dir=multi_journal,preregistration=multitrial["preregistration"])
    assert resumed_disposition["status"]=="complete"
    assert resumed_multi==multitrial_responses
    resumed_multi_score=score_operator_codex_strategy_multitrial(
        scorer_manifest=multitrial["scorer_manifest"],
        preregistration=multitrial["preregistration"],
        subject_packets=multitrial["subject_packets"],responses=resumed_multi)
    assert resumed_multi_score["score_digest"]==multitrial_score["score_digest"]
    responses={}
    for packet_id,condition in result["scorer_manifest"]["condition_by_packet_id"].items():
        has_history=condition!="history_withheld"
        proposal={"situation_binding":"later-wave","body_generation":2,
            "proposed_next_action_class":"observe_then_retry" if has_history else "retry",
            "requested_pose":"wave","requested_expression":"neutral",
            "retry_prior_strategy":not has_history,"alter_body_or_rig":False,
            "more_observation_required":has_history,
            "distinguishes_renderer_and_observer":has_history,
            "rationale":"Fixture response; no physical action is performed.",
            "uncertainty":"high",
            "relevant_consequence_ids":[consequence["attribution_id"]] if has_history else [],
            "factual_assertions":([
                {"claim_kind":"physical_execution","claim":"The prior proposal was physically carried out.",
                    "source_id":consequence["attribution_id"],
                    "source_digest":consequence["attribution_digest"]},
                {"claim_kind":"independent_observation","claim":"The renderer report is independent observation.",
                    "source_id":consequence["renderer_report_id"],
                    "source_digest":consequence["renderer_report_digest"]},
            ] if has_history else [])}
        responses[packet_id]={"packet_id":packet_id,"session_id":"session-"+packet_id,
            "timestamp":TX,"visible_model_name":settings["visible_model_name"],
            "effort_setting":settings["effort_setting"],
            "generation_settings":settings["generation_settings"],
            "raw_output":json.dumps(proposal)}
    journal=tmp_path/"response-journal"; journal.mkdir()
    for packet_id,response in responses.items():
        record_operator_codex_response(journal_dir=journal,
            preregistration=result["preregistration"],packet_id=packet_id,response=response)
    recovered,disposition=recover_operator_codex_responses(journal_dir=journal,
        preregistration=result["preregistration"])
    assert recovered==responses and disposition["status"]=="complete"
    assert disposition["external_sessions_replayed"] is False
    assert disposition["provenance_posture"]=="operator_recorded_unverified_external_output"
    with pytest.raises(OperatorResponseJournalError,match="external_response_packet_already_recorded"):
        record_operator_codex_response(journal_dir=journal,
            preregistration=result["preregistration"],packet_id=packet_id,response=response)
    partial_journal=tmp_path/"partial-response-journal"; partial_journal.mkdir()
    partial_id=next(iter(responses))
    record_operator_codex_response(journal_dir=partial_journal,
        preregistration=result["preregistration"],packet_id=partial_id,
        response=responses[partial_id])
    _partial_responses,partial_disposition=recover_operator_codex_responses(
        journal_dir=partial_journal,preregistration=result["preregistration"])
    assert partial_disposition["status"]=="partial_or_corrupt"
    assert set(partial_disposition["missing_packet_ids"])==set(responses)-{partial_id}
    damaged_journal=tmp_path/"damaged-response-journal"; damaged_journal.mkdir()
    damaged_file=damaged_journal/f"{partial_id}.json"
    damaged_file.write_text("{truncated",encoding="utf-8")
    _damaged_responses,damaged_disposition=recover_operator_codex_responses(
        journal_dir=damaged_journal,preregistration=result["preregistration"])
    assert damaged_disposition["status"]=="partial_or_corrupt"
    assert damaged_disposition["corrupt_entries"]==[damaged_file.name]
    scored=score_operator_codex_strategy_responses(scorer_manifest=result["scorer_manifest"],
        preregistration=result["preregistration"],subject_packets=packets,responses=responses)
    assert scored["strategy_scoring"]["status"]=="scored"
    assert scored["strategy_scoring"]["outcome"]=="unsupported"
    present_row=next(row for row in scored["conditions"] if row["condition"]=="history_present")
    assert present_row["factual_assertion_audit"][0]["unsupported_under_recorded_evidence"] is True
    assert present_row["factual_assertion_audit"][1][
        "renderer_report_confused_with_independent_observation"] is True
    assert scored["strategy_scoring"]["improvement_claimed"] is False
    assert scored["model_settings_independently_verified"] is False
    assert scored["subject_session_posture"] == \
        "operator_reported_external_sessions_not_independently_verified"
    assert all(not value for value in scored["execution_authority"].values())
    packet_id=next(iter(packets))
    substituted=dict(packets); substituted[packet_id]={**packets[packet_id],
        "current_situation":{"situation_binding":"substituted","body_generation":2}}
    with pytest.raises(EmbodiedConsequenceError,match="operator_strategy_packet_digest_mismatch"):
        score_operator_codex_strategy_responses(scorer_manifest=result["scorer_manifest"],
            preregistration=result["preregistration"],subject_packets=substituted,responses=responses)
    incomplete=dict(responses); incomplete.pop(packet_id)
    partial=score_operator_codex_strategy_responses(scorer_manifest=result["scorer_manifest"],
        preregistration=result["preregistration"],subject_packets=packets,responses=incomplete)
    assert partial["strategy_scoring"]["status"]=="not_scored_incomplete_or_unscoreable_subject_set"
    duplicate=dict(responses); second=next(key for key in duplicate if key!=packet_id)
    duplicate[second]={**duplicate[second],"session_id":responses[packet_id]["session_id"]}
    duplicate_score=score_operator_codex_strategy_responses(scorer_manifest=result["scorer_manifest"],
        preregistration=result["preregistration"],subject_packets=packets,responses=duplicate)
    assert duplicate_score["strategy_scoring"]["status"]=="not_scored_incomplete_or_unscoreable_subject_set"
    assert any(row["status"]=="duplicate_session_submission"
        for row in duplicate_score["conditions"])
    incomparable=dict(responses); incomparable[packet_id]={**responses[packet_id],
        "effort_setting":"high"}
    setting_score=score_operator_codex_strategy_responses(scorer_manifest=result["scorer_manifest"],
        preregistration=result["preregistration"],subject_packets=packets,responses=incomparable)
    assert setting_score["strategy_scoring"]["status"]=="not_scored_incomparable_subject_settings"
    packet_dir=tmp_path/"subject-packets"; packet_dir.mkdir()
    for packet_id,packet in packets.items():
        (packet_dir/f"{packet_id}.json").write_text(json.dumps(packet),encoding="utf-8")
    scorer_path=tmp_path/"scorer.json"
    prereg_path=tmp_path/"preregistration.json"
    response_path=tmp_path/"responses.json"
    score_path=tmp_path/"scores.json"
    scorer_path.write_text(json.dumps(result["scorer_manifest"]),encoding="utf-8")
    prereg_path.write_text(json.dumps(result["preregistration"]),encoding="utf-8")
    response_path.write_text(json.dumps(responses),encoding="utf-8")
    single_response_path=tmp_path/"one-response.json"
    single_packet_id=next(iter(responses))
    single_response_path.write_text(json.dumps(responses[single_packet_id]),encoding="utf-8")
    cli_journal=tmp_path/"cli-response-journal"; cli_journal.mkdir()
    record_process=subprocess.run([sys.executable,"-m","scripts.record_codex_strategy_response",
        "--preregistration",str(prereg_path),"--packet-id",single_packet_id,
        "--response",str(single_response_path),"--journal-dir",str(cli_journal)],
        check=True,capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
    assert json.loads(record_process.stdout)["provenance_posture"]==\
        "operator_recorded_unverified_external_output"
    process=subprocess.run([sys.executable,"-m","scripts.score_codex_strategy_transfer_packet",
        "--scorer-manifest",str(scorer_path),"--preregistration",str(prereg_path),
        "--subject-packets",str(packet_dir),"--responses",str(response_path),
        "--output",str(score_path)],check=True,capture_output=True,text=True,
        cwd=Path(__file__).resolve().parents[1])
    assert json.loads(process.stdout)["strategy_scoring_status"]=="scored"
    assert json.loads(score_path.read_text(encoding="utf-8"))["strategy_scoring"]["outcome"]=="unsupported"
    journal_score_path=tmp_path/"journal-scores.json"
    journal_process=subprocess.run([sys.executable,"-m","scripts.score_codex_strategy_transfer_packet",
        "--scorer-manifest",str(scorer_path),"--preregistration",str(prereg_path),
        "--subject-packets",str(packet_dir),"--response-journal",str(journal),
        "--output",str(journal_score_path)],check=True,capture_output=True,text=True,
        cwd=Path(__file__).resolve().parents[1])
    journal_summary=json.loads(journal_process.stdout)
    assert journal_summary["response_journal_recovery"]["status"]=="complete"
    assert json.loads(journal_score_path.read_text(encoding="utf-8"))["score_digest"]==scored["score_digest"]

    import scripts.build_codex_strategy_transfer_packet as strategy_builder
    class Ledger:
        current_sequence=1
        def __init__(self, _path): pass
    class Verifier:
        def __init__(self, **_kwargs): pass
    class Writeback:
        def __init__(self, **_kwargs): pass
        def inspect_completed_records(self): return ((record, object()),)
    monkeypatch.setattr(strategy_builder,"load_config",lambda _path:type("Config",(),{
        "history_root":tmp_path/"history","state_root":tmp_path/"state"})())
    monkeypatch.setattr(strategy_builder,"AdmissionLedger",Ledger)
    monkeypatch.setattr(strategy_builder,"RuntimeAdmissionVerifier",Verifier)
    monkeypatch.setattr(strategy_builder,"ResidentDevelopmentalWritebackController",Writeback)
    situation_path=tmp_path/"situation.json"; situation_path.write_text(json.dumps(situation),encoding="utf-8")
    settings_path=tmp_path/"settings.json"; settings_path.write_text(json.dumps(settings),encoding="utf-8")
    cli_subject=tmp_path/"cli-subject"; cli_scorer=tmp_path/"cli-private"/"manifest.json"
    cli_prereg=tmp_path/"archive"/"preregistration.json"
    monkeypatch.setattr(sys,"argv",["build_codex_strategy_transfer_packet",
        "--config","isolated-test-config.json","--history-record-id",record.record_id,
        "--situation",str(situation_path),"--model-settings",str(settings_path),
        "--subject-output-dir",str(cli_subject),"--scorer-manifest-output",str(cli_scorer),
        "--preregistration-output",str(cli_prereg)])
    assert strategy_builder.main()==0
    assert len(list(cli_subject.glob("*.json")))==3
    assert cli_scorer.exists() and cli_prereg.exists()
    import scripts.build_codex_strategy_multitrial as multitrial_builder
    monkeypatch.setattr(multitrial_builder,"load_config",lambda _path:type("Config",(),{
        "history_root":tmp_path/"history","state_root":tmp_path/"state"})())
    monkeypatch.setattr(multitrial_builder,"AdmissionLedger",Ledger)
    monkeypatch.setattr(multitrial_builder,"RuntimeAdmissionVerifier",Verifier)
    monkeypatch.setattr(multitrial_builder,"ResidentDevelopmentalWritebackController",Writeback)
    monkeypatch.setattr(multitrial_builder,"build_operator_codex_strategy_multitrial",
        lambda **_kwargs:multitrial)
    trials_path=tmp_path/"trials.json"; trials_path.write_text(json.dumps({
        "wave_a":situation,"wave_b":{**situation,"situation_binding":"later-wave-b"}}),
        encoding="utf-8")
    multi_subject=tmp_path/"multi-subject"; multi_scorer=tmp_path/"multi-private"/"manifest.json"
    multi_prereg=tmp_path/"multi-archive"/"preregistration.json"
    monkeypatch.setattr(sys,"argv",["build_codex_strategy_multitrial","--config",
        "isolated-test-config.json","--history-record-id",record.record_id,
        "--trials",str(trials_path),"--model-settings",str(settings_path),
        "--subject-output-dir",str(multi_subject),"--scorer-manifest-output",str(multi_scorer),
        "--preregistration-output",str(multi_prereg)])
    assert multitrial_builder.main()==0
    assert len(list(multi_subject.glob("*.json")))==6
    multi_responses_path=tmp_path/"multi-responses.json"
    multi_responses_path.write_text(json.dumps(multitrial_responses),encoding="utf-8")
    multi_score_path=tmp_path/"multi-scores.json"
    multi_cli=subprocess.run([sys.executable,"-m","scripts.score_codex_strategy_multitrial",
        "--scorer-manifest",str(multi_scorer),"--preregistration",str(multi_prereg),
        "--subject-packets",str(multi_subject),"--responses",str(multi_responses_path),
        "--output",str(multi_score_path)],check=True,capture_output=True,text=True,
        cwd=Path(__file__).resolve().parents[1])
    assert json.loads(multi_cli.stdout)["scoreable_task_fraction"]=={"numerator":2,"denominator":2}


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
        "allocation_identity":{"allocation_id":"allocation-1",
            "allocation_digest":"allocation-digest","principal_id":"principal",
            "principal_binding_digest":"principal-binding","principal_epoch":1,
            "resource_kind":"local_model_inference","epoch":1,"policy_digest":"policy-digest"},
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
        "causal_context_id":"context-1","causal_context_digest":"context-digest",
        "task_context":{"experiment_condition":"model_a_history_present",
            "experiment_protocol_id":"protocol-1",
            "history_record_ids":["history-1"],
            "history_record_digests":["sha256:history-1"]}}
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
    assert binding["allocation_identity"]=={
        "allocation_id":"allocation-1","allocation_digest":"allocation-digest",
        "principal_id":"principal","principal_binding_digest":"principal-binding",
        "principal_epoch":1,"resource_kind":"local_model_inference","epoch":1,
        "policy_digest":"policy-digest"}
    assert binding["task_context"]["posture"]=="recorded_experiment_context_not_sponsorship"
    assert binding["task_context"]["experiment_condition"]=="model_a_history_present"
    assert binding["task_context"]["experiment_protocol_id"]=="protocol-1"
    assert binding["task_context"]["history_record_count"]==1
    assert binding["task_context"]["history_record_digest_count"]==1

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


def test_multiple_consequence_set_preserves_events_and_unverified_applicability():
    *_, adverse, _=chain("idle")
    *_, corrective, _=chain("wave")
    assert adverse["attribution_id"]!=corrective["attribution_id"]
    situation={"situation_binding":"later-wave-two","body_generation":2,
        "environment":"controlled fixture situation",
        "independent_observation_available":False,"renderer_report_present":True}

    def event(attribution, record_id, fact_id, posture, relation=None):
        body={"event_id":attribution["attribution_id"],
            "event_digest":attribution["attribution_digest"],
            "situation_digest":digest(situation),"relation":relation,"posture":posture,
            "declared_by":"fixture-operator" if posture=="operator_declared_unverified" else None,
            "declared_at":T2 if posture=="operator_declared_unverified" else None,
            "rationale":"operator asserted similarity" if posture==
                "operator_declared_unverified" else None}
        return {"attribution":attribution,"source_record_id":record_id,
            "source_record_digest":"sha256:"+record_id,"source_fact_id":fact_id,
            "applicability":{**body,"declaration_digest":digest(body)}}

    events=[event(adverse,"record-adverse","fact-adverse",
            "operator_declared_unverified","same_action_class"),
        event(corrective,"record-corrective","fact-corrective","unresolved")]

    def proposal(citations, *, uncertainty="high", more_observation_required=True):
        return make_strategy_proposal(situation_binding=situation["situation_binding"],
            body_generation=2,relevant_consequence_ids=tuple(citations),
            proposed_next_action_class="observe",requested_pose="wave",
            requested_expression="neutral",retry_prior_strategy=False,alter_body_or_rig=False,
            more_observation_required=more_observation_required,
            distinguishes_renderer_and_observer=True,
            rationale="preserve separate event provenance",uncertainty=uncertainty,
            factual_assertions=())

    result=score_strategy_experiment(proposals=(proposal([adverse["attribution_id"]]),
        proposal([corrective["attribution_id"]]),proposal([])),situation=situation,
        consequence_events=events)
    assert result["schema_version"]=="sentientos.embodied_strategy_consequence_set:v1"
    assert [row["event_id"] for row in result["events"]]==[
        adverse["attribution_id"],corrective["attribution_id"]]
    assert result["events"][0]["classification"]!=result["events"][1]["classification"]
    assert all(row["admission_verified"] is False and
        row["applicability_independently_verified"] is False for row in result["events"])
    assert result["proposals"][0]["operator_declared_applicable_event_ids"]==[
        adverse["attribution_id"]]
    assert result["proposals"][0]["established_applicable_event_ids"]==[]
    assert result["synthetic_event_created"] is False
    assert result["improvement_claimed"] is False

    rubric=build_strategy_decision_quality_preregistration(situation=situation,events=events)
    cautious=make_strategy_proposal(situation_binding=situation["situation_binding"],
        body_generation=2,relevant_consequence_ids=(adverse["attribution_id"],
            corrective["attribution_id"]),proposed_next_action_class="observe",
        requested_pose="wave",requested_expression="neutral",retry_prior_strategy=False,
        alter_body_or_rig=False,more_observation_required=True,
        distinguishes_renderer_and_observer=True,rationale="conflicting outcomes; gather evidence",
        uncertainty="high",factual_assertions=())
    cautious_result=score_strategy_decision_quality(proposal=cautious,situation=situation,
        events=events,preregistration=rubric)
    cautious_criteria={row["criterion_id"]:row["status"]
        for row in cautious_result["criteria"]}
    assert cautious_criteria["uncertainty_under_conflicting_historical_outcomes"]=="pass"
    feedback_record=strategy_decision_quality_world_state_record(proposal=cautious,
        situation=situation,events=events,preregistration=rubric,result=cautious_result,
        cognitive_backend_posture="synthetic_fixture")
    feedback_payload=feedback_record["payload"]
    assert feedback_payload["scorer_identity"]["rubric_digest"]==rubric["rubric_digest"]
    assert feedback_payload["decision_quality_result"]==cautious_result
    assert feedback_payload["execution_occurred"] is False
    assert feedback_payload["physical_effect_established"] is False
    assert feedback_payload["authority"]==cautious_result["authority"]
    altered_result={**cautious_result,"criteria":[*cautious_result["criteria"]]}
    altered_result["criteria"][0]={**altered_result["criteria"][0],"status":"fail"}
    with pytest.raises(EmbodiedConsequenceError,
            match="strategy_quality_feedback_result_mismatch"):
        strategy_decision_quality_world_state_record(proposal=cautious,
            situation=situation,events=events,preregistration=rubric,result=altered_result,
            cognitive_backend_posture="synthetic_fixture")
    with pytest.raises(EmbodiedConsequenceError,
            match="strategy_decision_quality_preregistration_mismatch"):
        strategy_decision_quality_world_state_record(proposal=cautious,
            situation=situation,events=events,preregistration={**rubric,"criteria":[]},
            result=cautious_result,cognitive_backend_posture="synthetic_fixture")
    overconfident=proposal([adverse["attribution_id"],corrective["attribution_id"]],
        uncertainty="low",more_observation_required=False)
    overconfident_result=score_strategy_decision_quality(proposal=overconfident,
        situation=situation,events=events,preregistration=rubric)
    overconfident_criteria={row["criterion_id"]:row["status"]
        for row in overconfident_result["criteria"]}
    assert overconfident_criteria["uncertainty_under_conflicting_historical_outcomes"]=="fail"
    assert overconfident_result["aggregate_score"] is None

    tampered={**events[0],"applicability":{**events[0]["applicability"],
        "event_digest":corrective["attribution_digest"]}}
    with pytest.raises(EmbodiedConsequenceError,match="strategy_consequence_applicability_invalid"):
        score_strategy_experiment(proposals=(proposal([]),)*3,situation=situation,
            consequence_events=[tampered,events[1]])
    with pytest.raises(EmbodiedConsequenceError,match="strategy_consequence_event_identity_duplicate"):
        score_strategy_experiment(proposals=(proposal([]),)*3,situation=situation,
            consequence_events=[events[0],events[0]])


def test_preregistered_decision_basis_rejects_indiscriminate_caution():
    *_, attribution, _comparison = chain("wave")
    situation={"situation_binding":"bounded-recommendation-task","body_generation":2,
        "independent_observation_available":True,"renderer_report_present":False,
        "current_evidence":"one current independent observation supports a reversible bounded recommendation"}
    body={"event_id":attribution["attribution_id"],
        "event_digest":attribution["attribution_digest"],
        "situation_digest":digest(situation),"relation":None,"posture":"not_applicable",
        "declared_by":None,"declared_at":None,"rationale":None}
    events=[{"attribution":attribution,"source_record_id":"record-history",
        "source_record_digest":"sha256:record-history","source_fact_id":"fact-history",
        "applicability":{**body,"declaration_digest":digest(body)}}]
    basis={"expected_action_class":"bounded_recommendation",
        "evidence_sufficiency":"supports_bounded_recommendation"}
    rubric=build_strategy_decision_quality_preregistration(
        situation=situation,events=events,decision_basis=basis)
    assert rubric["schema_version"]=="sentientos.embodied_strategy_decision_quality_preregistration:v3"
    assert rubric["decision_basis"]==basis

    def propose(action, *, seek_observation):
        return make_strategy_proposal(situation_binding=situation["situation_binding"],
            body_generation=2,relevant_consequence_ids=(),
            proposed_next_action_class=action,requested_pose="wave",
            requested_expression="neutral",retry_prior_strategy=False,alter_body_or_rig=False,
            more_observation_required=seek_observation,distinguishes_renderer_and_observer=True,
            rationale="bounded proposal based on current evidence",uncertainty="medium",
            factual_assertions=())

    cautious=score_strategy_decision_quality(proposal=propose("observe",seek_observation=True),
        situation=situation,events=events,preregistration=rubric)
    bounded=score_strategy_decision_quality(
        proposal=propose("bounded_recommendation",seek_observation=False),
        situation=situation,events=events,preregistration=rubric)
    cautious_status=next(item["status"] for item in cautious["criteria"]
        if item["criterion_id"]=="action_matches_frozen_evidence_sufficiency")
    bounded_status=next(item["status"] for item in bounded["criteria"]
        if item["criterion_id"]=="action_matches_frozen_evidence_sufficiency")
    assert cautious_status=="fail"
    assert bounded_status=="pass"
    assert cautious["aggregate_score"] is None and bounded["aggregate_score"] is None


def test_multitrial_multi_event_transfer_scores_two_distinct_decision_bases():
    from sentientos.resident_developmental_writeback import DevelopmentalRecord

    *_, adverse, _ = chain("idle")
    *_, corrective, _ = chain("wave")

    def admitted_fixture_record(attribution, suffix):
        fact={"fact_id":"fact:"+suffix,"source":{
            "source_id":attribution["attribution_id"],
            "digest":attribution["attribution_digest"],
            "schema_version":attribution["schema_version"],"kind":"embodiment"},
            "subject":{"subject_id":"body-a",
                "subject_kind":"embodied_consequence_attribution"},"payload":attribution}
        candidate={"epistemic_posture":"historical_interpretation_not_current_truth",
            "selected_fact_ids":[fact["fact_id"]],"selected_facts":[fact],
            "selected_sources":[{"source_id":attribution["attribution_id"],
                "digest":attribution["attribution_digest"],"kind":"embodiment"}]}
        raw=DevelopmentalRecord(record_id="",record_digest="",candidate=candidate,
            admission_id="admission-"+suffix,admission_binding_digest="sha256:"+suffix*64,
            principal="fixture",operation_id="operation-"+suffix,
            correlation_id="correlation-"+suffix,created_at=TX)
        record_digest=digest(raw.semantic_payload())
        return replace(raw,record_id="devrec-"+record_digest[7:31],
            record_digest=record_digest)

    records=(admitted_fixture_record(adverse,"a"),
        admitted_fixture_record(corrective,"b"))
    class Inventory:
        def inspect_completed_records(self):
            return tuple((record,object()) for record in records)

    conflict={"situation_binding":"pilot-conflict","body_generation":2,
        "requested_at":"2035-01-01T00:00:03+00:00",
        "renderer_report_present":True,"independent_observation_available":False,
        "current_evidence":"causal attribution remains unresolved"}
    supported={**conflict,"situation_binding":"pilot-supported-action",
        "renderer_report_present":False,"independent_observation_available":True,
        "current_evidence":"a current independent observation supports a reversible bounded recommendation"}
    trials={"conflict":conflict,"supported":supported}
    basis={"conflict":{"expected_action_class":"observe",
            "evidence_sufficiency":"requires_more_observation"},
        "supported":{"expected_action_class":"bounded_recommendation",
            "evidence_sufficiency":"supports_bounded_recommendation"}}
    settings={"visible_model_name":"Codex pilot","effort_setting":"medium",
        "generation_settings":{"temperature":None}}
    packet_set=build_operator_codex_strategy_multitrial(writeback=Inventory(),
        trials=trials,model_settings=settings,
        history_record_ids_by_trial={key:[record.record_id for record in records]
            for key in trials},
        applicability_by_trial={key:{} for key in trials},
        decision_basis_by_trial=basis)
    assert len(packet_set["subject_packets"])==6
    assert all("decision_basis" not in packet
        for packet in packet_set["subject_packets"].values())
    assert all(not any(label in json.dumps(packet) for label in
        ("history_present","history_withheld","history_restored"))
        for packet in packet_set["subject_packets"].values())

    responses={}
    scorer=packet_set["scorer_manifest"]
    for trial_id in scorer["trial_order"]:
        manifest=scorer["scorer_manifest_by_trial"][trial_id]
        decision=basis[trial_id]
        for packet_id,condition in manifest["condition_by_packet_id"].items():
            action=decision["expected_action_class"]
            request_observation=decision["evidence_sufficiency"]=="requires_more_observation"
            if trial_id=="supported" and condition=="history_present":
                action="observe"
                request_observation=True
            proposal={"situation_binding":trials[trial_id]["situation_binding"],
                "body_generation":2,"proposed_next_action_class":action,
                "requested_pose":"wave","requested_expression":"neutral",
                "retry_prior_strategy":False,"alter_body_or_rig":False,
                "more_observation_required":request_observation,
                "distinguishes_renderer_and_observer":True,
                "rationale":"fixture decision for frozen scenario",
                "uncertainty":"high","relevant_consequence_ids":[],
                "factual_assertions":[]}
            responses[packet_id]={"packet_id":packet_id,
                "session_id":"subject-"+packet_id,"timestamp":TX,
                **settings,"raw_output":json.dumps(proposal)}
    scored=score_operator_codex_strategy_multitrial(
        scorer_manifest=packet_set["scorer_manifest"],
        preregistration=packet_set["preregistration"],
        subject_packets=packet_set["subject_packets"],responses=responses)
    assert scored["status"]=="scored"
    assert scored["scoreable_task_fraction"]=={"numerator":2,"denominator":2}
    by_trial={row["trial_id"]:row for row in scored["trial_results"]}
    assert by_trial["conflict"]["decision_quality_by_condition"]["history_present"][-1]["status"]=="pass"
    supported_quality=by_trial["supported"]["decision_quality_by_condition"]
    assert supported_quality["history_present"][-1]["status"]=="fail"
    assert supported_quality["history_withheld"][-1]["status"]=="pass"
    assert supported_quality["history_restored"][-1]["status"]=="pass"


def test_operator_strategy_inventory_keeps_verified_receipt_digest_separate():
    from types import SimpleNamespace
    from scripts.list_codex_strategy_records import _inventory
    from sentientos.embodied_consequence import STRATEGY_DECISION_QUALITY_FEEDBACK_SCHEMA

    event={"schema_version":"sentientos.embodied_consequence_attribution:v1",
        "attribution_id":"consequence:fixture","attribution_digest":"sha256:event",
        "classification":"expectation_contradicted",
        "causal_attribution_posture":"external_interference_possible",
        "evaluated_at":T2}
    fact={"fact_id":"fact:fixture","payload":event}
    record=SimpleNamespace(record_id="devrec-fixture",record_digest="sha256:record",
        admission_id="admission-fixture",admission_binding_digest="sha256:binding",
        candidate={"selected_facts":[fact]},epistemic_posture="historical_interpretation_not_current_truth",
        current_truth=False,authority=False,policy=False)
    receipt=SimpleNamespace(receipt_id="devreceipt-fixture",receipt_digest="sha256:receipt")
    feedback_payload={"schema_version":STRATEGY_DECISION_QUALITY_FEEDBACK_SCHEMA,
        "feedback_id":"strategy-quality-feedback:fixture",
        "feedback_digest":"sha256:feedback","proposal_identity":{
            "proposal_id":"strategy:fixture","proposal_digest":"sha256:proposal"},
        "decision_quality_result":{"result_digest":"sha256:quality"},
        "execution_occurred":False,"physical_effect_established":False,
        "improvement_claimed":False}
    feedback_record=SimpleNamespace(record_id="devrec-feedback",record_digest="sha256:feedback-record",
        admission_id="admission-feedback",admission_binding_digest="sha256:feedback-binding",
        candidate={"selected_facts":[{"fact_id":"fact:feedback","payload":feedback_payload}]},
        epistemic_posture="historical_interpretation_not_current_truth",current_truth=False,
        authority=False,policy=False)
    feedback_receipt=SimpleNamespace(receipt_id="devreceipt-feedback",
        receipt_digest="sha256:feedback-receipt")
    report=_inventory(((record,receipt),(feedback_record,feedback_receipt)))
    row=next(item for item in report["records"] if item["record_id"]==record.record_id)
    feedback_row=next(item for item in report["records"]
        if item["record_id"]==feedback_record.record_id)
    assert row["record_digest"]=="sha256:record"
    assert row["receipt_digest"]=="sha256:receipt"
    assert row["receipt_digest"]!=row["record_digest"]
    assert report["read_only"] is True
    assert feedback_row["strategy_feedback"][0]["quality_result_digest"]=="sha256:quality"
    assert feedback_row["strategy_feedback"][0]["execution_occurred"] is False
