from dataclasses import replace
import json
import pytest

from sentientos.governed_improvement_signal_plane import evaluate_signal_plane
from sentientos.maintenance_post_adoption_evaluation import (
    FALSE_AUTHORITY, MaintenancePostAdoptionEvaluationOwner, MeasurementDefinition,
    PostAdoptionEvaluationError, SuccessorQualification, make_baseline, make_protocol,
    post_adoption_epistemic_binding,
)
from sentientos.persistent_epistemic_state import PersistentEpistemicStateOwner, make_proposition

pytestmark=pytest.mark.no_legacy_skip
D="sha256:"+"a"*64


def protocol(*measurements):
    return make_protocol(maintenance_task_id="task-1",proposal_id="proposal-1",signal_ids=("signal-1",),
        implementation_session_id="session-1",validation_result_digest=D,landed_commit="commit-b",
        landed_tree="tree-b",predecessor_generation=4,expected_successor_generation=5,target_scope="capability:x",
        measurements=measurements or (MeasurementDefinition("target","fixture","fixture:v1","equals",True,False),),
        required_evidence_sources=("fixture",),observation_trigger={"kind":"resident_ready"},
        created_at="2026-01-01T00:00:00Z",creation_generation=4)


def baseline(p, observations):
    laws={m.observable_id:m.measurement_law for m in p.measurements}
    return make_baseline(p,source_revision="commit-a",source_tree="tree-a",runtime_identity="runtime-a",
        observations=observations,source_records={k:{"id":"pre-"+k,"digest":D} for k in observations},
        measurement_laws=laws,observed_at="2026-01-01T00:01:00Z",collector_id="deterministic-fixture")


def qualification(**changes):
    values=dict(successor_generation=5,successor_commit="commit-b",successor_tree="tree-b",generation_digest=D,
        continuity_receipt_digest=D,adoption_receipt_digest=D,launch_provenance_digest=D,readiness_receipt_digest=D,
        adoption_completed_at="2026-01-01T00:02:00Z",readiness_status="resident_adoption_completed")
    values.update(changes); return SuccessorQualification(**values)


def run(tmp_path, p, before, after):
    owner=MaintenancePostAdoptionEvaluationOwner(tmp_path); owner.preregister(p); b=baseline(p,before); owner.capture_baseline(p,b)
    laws={m.observable_id:m.measurement_law for m in p.measurements}
    o=owner.observe(p,b,qualification(),observations=after,source_records={k:{"id":"post-"+k,"digest":D} for k in after},measurement_laws=laws,observed_at="2026-01-01T00:03:00Z",collector_id="deterministic-fixture")
    return owner,owner.evaluate(p,b,o,evaluated_at="2026-01-01T00:04:00Z")


def test_satisfied_reconstructs_and_is_not_causal_proof(tmp_path):
    owner,result=run(tmp_path,protocol(),{"target":False},{"target":True})
    assert result.result=="target_expectation_satisfied"
    assert result.validation_result_digest==D and "not_experimental_causation" in result.attribution_posture
    assert MaintenancePostAdoptionEvaluationOwner(tmp_path).verify()=={"protocols":1,"baselines":1,"observations":1,"evaluations":1,"signals":0,"recommendations":0}


@pytest.mark.parametrize(("after","expected"), [({"target":False},"no_detectable_change"),({},"insufficient_evidence")])
def test_null_and_insufficient_are_retained(tmp_path,after,expected):
    _,result=run(tmp_path,protocol(),{"target":False},after); assert result.result==expected


def test_contradiction_routes_proposal_only_signal_with_lineage(tmp_path):
    p=protocol(MeasurementDefinition("count","fixture","fixture:v1","decrease",None,None))
    owner,result=run(tmp_path,p,{"count":2},{"count":3})
    assert result.result=="target_expectation_contradicted"
    record=owner._read("signals")[0]; evaluation=evaluate_signal_plane([record])
    assert evaluation.receipts[0].candidate_identified and record["repository_mutation_performed"] is False
    assert result.observation_digest in record["evidence_refs"]


def test_protected_regression_wins_and_rollback_is_recommendation_only(tmp_path):
    p=protocol(MeasurementDefinition("target","fixture","fixture:v1","equals",True,False),MeasurementDefinition("protected","fixture","fixture:v1","true",True,False,True))
    owner,result=run(tmp_path,p,{"target":False,"protected":True},{"target":True,"protected":False})
    assert result.result=="new_regression_observed"
    recommendation=owner.recommend_rollback(result,rationale="protected invariant failed",urgency="high")
    assert recommendation.executes_rollback is False and recommendation.operator_decision_required
    assert recommendation.authority==FALSE_AUTHORITY


def test_temporal_identity_measurement_authority_and_replay_fail_closed(tmp_path):
    p=protocol(); owner=MaintenancePostAdoptionEvaluationOwner(tmp_path); owner.preregister(p); b=baseline(p,{"target":False}); owner.capture_baseline(p,b)
    with pytest.raises(PostAdoptionEvaluationError,match="qualified"):
        owner.observe(p,b,qualification(successor_tree="wrong"),observations={"target":True},source_records={},measurement_laws={"target":"fixture:v1"},observed_at="2026-01-01T00:03:00Z",collector_id="fixture")
    with pytest.raises(PostAdoptionEvaluationError,match="preregistered"):
        owner.observe(p,b,qualification(adoption_completed_at="2025-01-01T00:00:00Z"),observations={"target":True},source_records={},measurement_laws={"target":"fixture:v1"},observed_at="2026-01-01T00:03:00Z",collector_id="fixture")
    with pytest.raises(PostAdoptionEvaluationError,match="law"):
        owner.observe(p,b,qualification(),observations={"target":True},source_records={},measurement_laws={"target":"other:v1"},observed_at="2026-01-01T00:03:00Z",collector_id="fixture")
    with pytest.raises(PostAdoptionEvaluationError,match="authority"):
        owner.preregister(replace(p,authority={**FALSE_AUTHORITY,"rollback":True}))
    laws={"target":"fixture:v1"}; o=owner.observe(p,b,qualification(),observations={"target":True},source_records={"target":{"id":"x","digest":D}},measurement_laws=laws,observed_at="2026-01-01T00:03:00Z",collector_id="fixture")
    owner.evaluate(p,b,o,evaluated_at="2026-01-01T00:04:00Z")
    with pytest.raises(PostAdoptionEvaluationError,match="replay"):
        owner.observe(p,b,qualification(),observations={"target":True},source_records={},measurement_laws=laws,observed_at="2026-01-01T00:05:00Z",collector_id="fixture")


def test_tamper_fails_reconstruction_and_epistemic_adapter_uses_owner(tmp_path):
    owner,result=run(tmp_path/"evaluation",protocol(),{"target":False},{"target":True})
    path=next((tmp_path/"evaluation"/"evaluations").glob("*.json")); raw=json.loads(path.read_text()); raw["result"]="target_expectation_contradicted"; path.write_text(json.dumps(raw))
    with pytest.raises(PostAdoptionEvaluationError): MaintenancePostAdoptionEvaluationOwner(tmp_path/"evaluation")
    epistemic=PersistentEpistemicStateOwner(tmp_path/"epistemic",allowed_namespaces=["maintenance"])
    proposition=make_proposition(namespace="maintenance",subject="task-1",predicate="successor_consequence",object_value={"generation":5,"protocol":result.protocol_digest},polarity="positive",qualifiers={},temporal_scope={"generation":5},context_scope={"protocol":result.protocol_id},proposition_class="predictive")
    epistemic.register_proposition(proposition); binding=post_adoption_epistemic_binding(proposition_id=proposition.proposition_id,evaluation=result,observed_at=result.evaluated_at); epistemic.bind_evidence(binding)
    state,_=epistemic.commit_update(proposition_id=proposition.proposition_id,expected_predecessor_digest=None,stance="provisionally_supported",reason="new_evidence",active_binding_ids=[binding.binding_id],added_binding_ids=[binding.binding_id],correlation_id=result.evaluation_id,tick=5,recorded_at="2026-01-01T00:05:00Z")
    assert state.proposition_id==proposition.proposition_id
