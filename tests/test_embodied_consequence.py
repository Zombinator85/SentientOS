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
        if claim.predicate==