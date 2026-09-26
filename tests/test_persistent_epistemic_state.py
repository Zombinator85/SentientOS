from dataclasses import replace
import json

import pytest

from sentientos.persistent_epistemic_state import (
    FALSE_AUTHORITY, EpistemicStateError, PersistentEpistemicStateOwner,
    PropositionRelation, evidence_posture, make_cognitive_projection,
    make_evidence_binding, make_proposition,
)

pytestmark = pytest.mark.no_legacy_skip


def proposition(statement="wording one", **scope):
    return make_proposition(namespace="embodiment", subject="body:g1", predicate="command_observed_pose",
        object_value={"pose":"wave"}, polarity="positive", qualifiers={"renderer":"fixture-r"},
        temporal_scope={"kind":"bounded_trial"}, context_scope={"fixture":"E", **scope},
        proposition_class="predictive", statement=statement)


def binding(p, source, relation="supports", dependency="independently_sourced_observation", upstream=(), freshness="current"):
    return make_evidence_binding(proposition_id=p.proposition_id, source_artifact_id=source,
        source_digest="sha256:"+source.zfill(64), source_schema="sentientos.test_observation:v1",
        source_class="independent_fixture", observation_time="2026-01-01T00:00:00Z",
        evidence_relation=relation, dependency_kind=dependency, dependency_group=source,
        upstream_binding_ids=upstream, freshness=freshness, reliability_posture=relation)


def test_semantic_identity_ignores_display_wording_and_mutation_fails(tmp_path):
    a, b = proposition("first"), proposition("equivalent display")
    assert a.proposition_id == b.proposition_id
    owner=PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"]); owner.register_proposition(a)
    with pytest.raises(EpistemicStateError, match="identity"):
        owner.register_proposition(replace(a, predicate="different"))


def test_attributable_chain_cas_dependency_noop_restart_and_tamper(tmp_path):
    owner=PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"]); p=proposition(); owner.register_proposition(p)
    a,event_a=owner.commit_update(proposition_id=p.proposition_id, expected_predecessor_digest=None,
        stance="unknown", reason="initialization", active_binding_ids=(), correlation_id="A", tick=1, recorded_at="2026-01-01T00:00:00Z")
    contradiction=binding(p,"1","contradicts"); owner.bind_evidence(contradiction)
    b,_=owner.commit_update(proposition_id=p.proposition_id, expected_predecessor_digest=a.state_digest,
        stance="contradicted", reason="contradiction_arrival", active_binding_ids=[contradiction.binding_id],
        added_binding_ids=[contradiction.binding_id], correlation_id="B",tick=2,recorded_at="2026-01-01T00:00:01Z")
    support=binding(p,"2"); owner.bind_evidence(support)
    c,_=owner.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=b.state_digest,
        stance="contested",reason="new_evidence",active_binding_ids=[contradiction.binding_id,support.binding_id],
        added_binding_ids=[support.binding_id],correlation_id="C",tick=3,recorded_at="2026-01-01T00:00:02Z")
    duplicate=binding(p,"3",dependency="shared_upstream_evidence",upstream=(support.binding_id,)); owner.bind_evidence(duplicate)
    d,_=owner.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=c.state_digest,
        stance="contested",reason="dependency_correction",active_binding_ids=[contradiction.binding_id,support.binding_id,duplicate.binding_id],
        added_binding_ids=[duplicate.binding_id],dependency_changes={duplicate.binding_id:"shared_upstream_evidence"},correlation_id="D",tick=4,recorded_at="2026-01-01T00:00:03Z")
    # A duplicate can cause an attributable no-op; it does not force confidence movement.
    e,_=owner.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=d.state_digest,
        stance=d.stance,reason="duplicate_evidence_correction",active_binding_ids=[contradiction.binding_id,support.binding_id,duplicate.binding_id],
        correlation_id="E",tick=5,recorded_at="2026-01-01T00:00:04Z")
    assert e.stance == d.stance and evidence_posture(owner.bindings(p.proposition_id))["posture"] == "mixed"
    with pytest.raises(EpistemicStateError,match="compare_and_swap"):
        owner.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=c.state_digest,stance="supported",reason="new_evidence",active_binding_ids=[],correlation_id="stale",tick=6,recorded_at="2026-01-01T00:00:05Z")
    assert PersistentEpistemicStateOwner(tmp_path,allowed_namespaces=["embodiment"]).verify()["updates"] == 5
    state_path=next((tmp_path/"states").glob("*.json")); altered=json.loads(state_path.read_text()); altered["stance"]="supported"; state_path.write_text(json.dumps(altered))
    with pytest.raises(EpistemicStateError): PersistentEpistemicStateOwner(tmp_path,allowed_namespaces=["embodiment"])


def test_refinement_preserves_old_evidence_and_temporal_firewall(tmp_path):
    owner=PersistentEpistemicStateOwner(tmp_path,allowed_namespaces=["embodiment"]); broad=proposition(); narrow=proposition(renderer_version="2")
    owner.register_proposition(broad); owner.register_proposition(narrow)
    old=binding(broad,"4"); owner.bind_evidence(old)
    owner.add_relation(PropositionRelation(narrow.proposition_id,broad.proposition_id,"narrows","2026-01-01T00:00:00Z"))
    state,_=owner.commit_update(proposition_id=narrow.proposition_id,expected_predecessor_digest=None,stance="unknown",reason="proposition_refinement",active_binding_ids=[],correlation_id="r",tick=8,recorded_at="2026-01-01T00:00:00Z")
    assert owner.bindings(narrow.proposition_id) == () and owner.bindings(broad.proposition_id)[0].binding_id == old.binding_id
    with pytest.raises(EpistemicStateError,match="same_tick"):
        make_cognitive_projection([state],source_tick=8,current_tick=8)
    projection=make_cognitive_projection([state],source_tick=8,current_tick=9)
    assert projection.current_truth is projection.authority is False


def test_authority_and_fabricated_or_missing_evidence_fail_closed(tmp_path):
    owner=PersistentEpistemicStateOwner(tmp_path,allowed_namespaces=["embodiment"]); p=proposition(); owner.register_proposition(p)
    with pytest.raises(EpistemicStateError,match="authority"):
        make_evidence_binding(proposition_id=p.proposition_id,source_artifact_id="model-text",source_digest="sha256:x",source_schema="model.free_text:v1",source_class="model_text",observation_time="2026-01-01T00:00:00Z",evidence_relation="supports",dependency_kind="unknown_dependency",dependency_group=None,upstream_binding_ids=(),freshness="current",reliability_posture="unknown",authority={**FALSE_AUTHORITY,"permission":True})
    with pytest.raises(EpistemicStateError,match="not_found"):
        owner.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=None,stance="supported",reason="new_evidence",active_binding_ids=["missing"],correlation_id="x",tick=1,recorded_at="2026-01-01T00:00:00Z")
