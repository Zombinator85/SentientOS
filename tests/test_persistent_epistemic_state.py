from dataclasses import replace
import json

import pytest

from sentientos.private_file_custody import (
    PrivateFileCustodyError, list_bounded_json_names_at, open_private_directory,
)
from sentientos.persistent_epistemic_state import (
    FALSE_AUTHORITY, EpistemicStateError, PersistentEpistemicStateOwner,
    PropositionRelation, evidence_posture, make_cognitive_projection,
    make_evidence_binding, make_proposition, make_epistemic_update_candidate, _write_new,
    MeaningBearingEpistemicCognitiveProjection, semantic_packets_for_projection,
    validate_cognitive_projection,
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


def test_owner_projection_is_verified_latest_bounded_deterministic_and_empty(tmp_path):
    owner=PersistentEpistemicStateOwner(tmp_path,allowed_namespaces=["embodiment"])
    assert owner.cognitive_projection(max_states=2) is None
    propositions=[proposition(index=index) for index in range(3)]
    for index,p in enumerate(reversed(propositions)):
        owner.register_proposition(p)
        first,_=owner.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=None,
            stance="unknown",reason="initialization",active_binding_ids=[],correlation_id=f"a-{index}",tick=index+1,
            recorded_at="2026-01-01T00:00:00Z")
        if index == 0:
            owner.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=first.state_digest,
                stance="suspended",reason="operator_error_correction",active_binding_ids=[],correlation_id="later",
                tick=9,recorded_at="2026-01-01T00:00:01Z")
    projection=owner.cognitive_projection(max_states=2)
    assert projection is not None
    assert projection.proposition_ids == tuple(sorted(p.proposition_id for p in propositions)[:2])
    assert len(projection.states) == 2
    manifest = projection.omission_manifest
    assert projection.schema_version == "sentientos.epistemic_cognitive_projection:v3"
    assert manifest is not None
    assert manifest["selection_limit"] == 2
    assert manifest["available_prior_state_count"] == 3
    assert manifest["selected_state_count"] == 2
    assert manifest["omitted_state_count"] == 1
    assert projection.source_tick == max(owner.update_events(p.proposition_id)[-1].tick
        for p in propositions)
    omitted_id = max(p.proposition_id for p in propositions)
    omitted_state = owner.current_state(omitted_id)
    assert omitted_state is not None
    omitted_event = owner.update_events(omitted_id)[-1]
    [omitted_identity] = manifest["omitted_state_identities"]
    assert omitted_identity == {
        "proposition_id": omitted_id,
        "state_id": omitted_state.state_id,
        "state_digest": omitted_state.state_digest,
        "generation": omitted_state.generation,
        "update_event_id": omitted_event.event_id,
        "update_tick": omitted_event.tick,
        "stance": omitted_state.stance,
        "dependency_unresolved": omitted_state.dependency_unresolved,
        "freshness": omitted_state.freshness,
        "updated_at": omitted_state.updated_at,
        "omission_reason": "projection_state_bound",
    }
    tampered_manifest = dict(manifest)
    tampered_row = dict(omitted_identity)
    tampered_row["state_digest"] = "sha256:" + "0" * 64
    tampered_manifest["omitted_state_identities"] = (tampered_row,)
    with pytest.raises(EpistemicStateError, match="omission"):
        validate_cognitive_projection(replace(projection,
            omission_manifest=tampered_manifest), require_meaning=True)
    assert projection.current_truth is projection.authority is projection.policy is projection.goal is False
    assert all(state["authority"] == FALSE_AUTHORITY for state in projection.states)

    event_path=next((tmp_path/"updates").glob("*.json"))
    event=json.loads(event_path.read_text()); event["tick"]=100; event_path.write_text(json.dumps(event))
    with pytest.raises(EpistemicStateError): owner.cognitive_projection(max_states=2)


def test_owner_projection_carries_exact_canonical_proposition_and_evidence_lineage(tmp_path):
    owner = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    propositions = [make_proposition(namespace="embodiment", subject="robot:g7",
        predicate="renderer_observed", object_value={"pose": "wave"}, polarity="positive",
        qualifiers={"renderer": "r1"}, temporal_scope={"window": window},
        context_scope={"location": place}, proposition_class="predictive",
        statement="exact canonical statement")
        for window, place in (("trial-a", "left"), ("trial-b", "right"))]
    states = []
    for index, proposition_value in enumerate(propositions):
        owner.register_proposition(proposition_value)
        support = binding(proposition_value, f"support-{index}")
        owner.bind_evidence(support)
        state, _ = owner.commit_update(proposition_id=proposition_value.proposition_id,
            expected_predecessor_digest=None, stance="provisionally_supported",
            reason="initialization", active_binding_ids=[support.binding_id],
            added_binding_ids=[support.binding_id],
            correlation_id=f"position-{index}", tick=index + 1,
            recorded_at="2026-01-01T00:00:00Z", confidence={"range": "wide"})
        states.append(state)
    projection = owner.cognitive_projection(max_states=2, current_tick=3)
    assert isinstance(projection, MeaningBearingEpistemicCognitiveProjection)
    assert projection.schema_version == "sentientos.epistemic_cognitive_projection:v2"
    assert projection.omission_manifest is None
    validate_cognitive_projection(projection, require_meaning=True)
    packets = semantic_packets_for_projection(projection)
    assert [packet["state"]["stance"] for packet in packets] == [
        "provisionally_supported", "provisionally_supported"]
    assert {packet["proposition"]["temporal_scope"]["window"] for packet in packets} == {
        "trial-a", "trial-b"}
    assert {packet["proposition"]["context_scope"]["location"] for packet in packets} == {
        "left", "right"}
    assert all(packet["proposition"]["proposition_digest"] ==
        next(p.proposition_digest for p in propositions
             if p.proposition_id == packet["proposition"]["proposition_id"])
        for packet in packets)
    recovered = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    replay = recovered.cognitive_projection(max_states=2, current_tick=3)
    assert replay is not None and replay.projection_digest == projection.projection_digest


def test_semantic_projection_rejects_substituted_meaning_and_bad_join(tmp_path):
    owner = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    proposition_value = proposition()
    owner.register_proposition(proposition_value)
    state, _ = owner.commit_update(proposition_id=proposition_value.proposition_id,
        expected_predecessor_digest=None, stance="unknown", reason="initialization",
        active_binding_ids=[], correlation_id="initial", tick=1,
        recorded_at="2026-01-01T00:00:00Z")
    projection = owner.cognitive_projection(max_states=1, current_tick=2)
    assert projection is not None
    substituted = dict(projection.propositions[0])
    substituted["context_scope"] = {"fixture": "substituted"}
    with pytest.raises(EpistemicStateError, match="semantic|digest|join"):
        validate_cognitive_projection(replace(projection,
            propositions=(substituted,)), require_meaning=True)
    mismatched_state = dict(projection.states[0])
    mismatched_state["proposition_id"] = "proposition:" + "0" * 24
    with pytest.raises(EpistemicStateError):
        validate_cognitive_projection(replace(projection, states=(mismatched_state,)),
            require_meaning=True)
    legacy = make_cognitive_projection([state], source_tick=1, current_tick=2)
    validate_cognitive_projection(legacy)
    assert not getattr(legacy, "schema_version", None)


def test_stale_position_keeps_stale_freshness_in_prior_packet(tmp_path):
    owner = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    p = proposition()
    owner.register_proposition(p)
    stale = binding(p, "stale-source", freshness="stale")
    owner.bind_evidence(stale)
    state, _ = owner.commit_update(proposition_id=p.proposition_id,
        expected_predecessor_digest=None, stance="provisionally_supported",
        reason="initialization", active_binding_ids=[stale.binding_id],
        added_binding_ids=[stale.binding_id], correlation_id="stale-prior", tick=4,
        recorded_at="2026-01-01T00:00:00Z")
    projection = owner.cognitive_projection(max_states=1, current_tick=5)
    assert projection is not None
    packet = semantic_packets_for_projection(projection)[0]
    assert packet["state"]["state_digest"] == state.state_digest
    assert packet["state"]["freshness"] == "stale"
    assert packet["interpretation_posture"] == "canonical_prior_position_not_current_truth"
    assert packet["evidence_posture"]["posture"] == "all_evidence_stale"



def test_incomplete_admission_bound_transaction_is_not_replayed_by_storage_owner(tmp_path):
    owner = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    p = proposition()
    owner.register_proposition(p)
    candidate = make_epistemic_update_candidate(
        proposition_id=p.proposition_id, predecessor_state_digest=None,
        proposed_stance="unknown", evidence_binding_ids=(), reason="initialization",
        rationale="explicit initialization", uncertainty="unknown", model_id=None,
        proposer_kind="deterministic_rule", proposer_id="recovery-fixture")
    state, event = owner.commit_update(
        proposition_id=p.proposition_id, expected_predecessor_digest=None,
        stance="unknown", reason="initialization", active_binding_ids=(),
        candidate=candidate, mutation_binding={
            "candidate_id": candidate.candidate_id, "candidate_digest": "sha256:fixture",
            "admission_id": "admission:fixture", "admission_binding_digest": "sha256:admission",
            "operation_id": "operation:fixture", "correlation_id": "correlation:fixture"},
        correlation_id="correlation:fixture", tick=1, recorded_at="2026-01-01T00:00:00Z")

    (tmp_path / "states" / f"{state.generation:012d}-{state.state_id}.json").unlink()
    (tmp_path / "updates" / f"{event.generation:012d}-{event.event_id}.json").unlink()

    recovered = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    assert recovered.current_state(p.proposition_id) is None
    recovered_counts = recovered.verify()
    assert recovered_counts["states"] == recovered_counts["updates"] == 0
    assert recovered_counts["incomplete_admission_bound_transactions"] == 1

    # Storage-only legacy transactions retain their established repair behavior.
    legacy_root = tmp_path / "legacy"
    legacy = PersistentEpistemicStateOwner(legacy_root, allowed_namespaces=["embodiment"])
    legacy_proposition = proposition(statement="legacy storage-only")
    legacy.register_proposition(legacy_proposition)
    legacy_state, legacy_event = legacy.commit_update(
        proposition_id=legacy_proposition.proposition_id,
        expected_predecessor_digest=None, stance="unknown", reason="initialization",
        active_binding_ids=(), correlation_id="legacy", tick=1,
        recorded_at="2026-01-01T00:00:00Z")
    (legacy_root / "states" / f"{legacy_state.generation:012d}-{legacy_state.state_id}.json").unlink()
    (legacy_root / "updates" / f"{legacy_event.generation:012d}-{legacy_event.event_id}.json").unlink()
    legacy_recovered = PersistentEpistemicStateOwner(
        legacy_root, allowed_namespaces=["embodiment"])
    assert legacy_recovered.current_state(legacy_proposition.proposition_id) == legacy_state

def test_authority_and_fabricated_or_missing_evidence_fail_closed(tmp_path):
    owner=PersistentEpistemicStateOwner(tmp_path,allowed_namespaces=["embodiment"]); p=proposition(); owner.register_proposition(p)
    with pytest.raises(EpistemicStateError,match="authority"):
        make_evidence_binding(proposition_id=p.proposition_id,source_artifact_id="model-text",source_digest="sha256:x",source_schema="model.free_text:v1",source_class="model_text",observation_time="2026-01-01T00:00:00Z",evidence_relation="supports",dependency_kind="unknown_dependency",dependency_group=None,upstream_binding_ids=(),freshness="current",reliability_posture="unknown",authority={**FALSE_AUTHORITY,"permission":True})
    with pytest.raises(EpistemicStateError,match="epistemic_evidence_delta_invalid"):
        owner.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=None,stance="supported",reason="new_evidence",active_binding_ids=["missing"],correlation_id="x",tick=1,recorded_at="2026-01-01T00:00:00Z")


def test_calibration_is_proposition_specific_and_temporally_bound(tmp_path):
    owner=PersistentEpistemicStateOwner(tmp_path,allowed_namespaces=["embodiment"]); a=proposition(a=1); b=proposition(b=2)
    owner.register_proposition(a); owner.register_proposition(b)
    state_a,_=owner.commit_update(proposition_id=a.proposition_id,expected_predecessor_digest=None,stance="unknown",reason="initialization",active_binding_ids=[],correlation_id="a",tick=1,recorded_at="2026-01-01T00:00:00Z")
    state_b,_=owner.commit_update(proposition_id=b.proposition_id,expected_predecessor_digest=None,stance="unknown",reason="initialization",active_binding_ids=[],correlation_id="b",tick=1,recorded_at="2026-01-01T00:00:00Z")
    evidence=binding(a,"9"); owner.bind_evidence(evidence)
    with pytest.raises(EpistemicStateError,match="proposition_mismatch"):
        owner.record_calibration(proposition_id=a.proposition_id,forecast_artifact_id="forecast",forecast_state_digest=state_b.state_digest,observed_outcome_id="outcome",comparison_result="contradicted",source_binding_ids=(evidence.binding_id,),resolved_at="2026-01-01T00:01:00Z")
    with pytest.raises(EpistemicStateError,match="not_after"):
        owner.record_calibration(proposition_id=a.proposition_id,forecast_artifact_id="forecast",forecast_state_digest=state_a.state_digest,observed_outcome_id="outcome",comparison_result="contradicted",source_binding_ids=(evidence.binding_id,),resolved_at="2025-01-01T00:00:00Z")
    event=owner.record_calibration(proposition_id=a.proposition_id,forecast_artifact_id="forecast",forecast_state_digest=state_a.state_digest,observed_outcome_id="outcome",comparison_result="contradicted",source_binding_ids=(evidence.binding_id,),resolved_at="2026-01-01T00:01:00Z")
    assert event.proposition_id==a.proposition_id and owner.verify()["calibrations"]==1


@pytest.mark.parametrize("tick", [-1, True])
def test_invalid_update_tick_cannot_publish_poisoned_transaction(tmp_path, tick):
    owner = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    p = proposition()
    owner.register_proposition(p)
    with pytest.raises(EpistemicStateError, match="epistemic_update_tick_invalid"):
        owner.commit_update(
            proposition_id=p.proposition_id, expected_predecessor_digest=None,
            stance="unknown", reason="initialization", active_binding_ids=(),
            correlation_id="invalid-tick", tick=tick, recorded_at="2026-01-01T00:00:00Z")
    assert list((tmp_path / "transactions").glob("*.json")) == []
    assert owner.verify()["updates"] == 0


def test_update_recorded_at_requires_bounded_aware_timestamp(tmp_path):
    owner = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    p = proposition()
    owner.register_proposition(p)
    with pytest.raises(EpistemicStateError, match="epistemic_recorded_at_invalid"):
        owner.commit_update(
            proposition_id=p.proposition_id, expected_predecessor_digest=None,
            stance="unknown", reason="initialization", active_binding_ids=(),
            correlation_id="invalid-time", tick=1, recorded_at="2026-01-01T00:00:00")
    assert list((tmp_path / "transactions").glob("*.json")) == []


def test_epistemic_collection_read_and_write_reject_symlinked_directory(tmp_path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("POSIX descriptor-bound publication is required")
    root = tmp_path / "owner"
    owner = PersistentEpistemicStateOwner(root, allowed_namespaces=("test",))
    target = tmp_path / "external"
    target.mkdir()
    original = root / "bindings"
    original.rename(root / "bindings-original")
    original.symlink_to(target, target_is_directory=True)

    with pytest.raises(EpistemicStateError, match="epistemic_collection_invalid"):
        owner._read("bindings")
    with pytest.raises(EpistemicStateError, match="epistemic_custody_root_invalid"):
        _write_new(original / "attacker.json", {"untrusted": True})
    assert list(target.iterdir()) == []


def test_epistemic_mutation_lock_rejects_symlink_and_shared_permissions(tmp_path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("POSIX no-follow lock custody is required")
    root = tmp_path / "owner"
    owner = PersistentEpistemicStateOwner(root, allowed_namespaces=("test",))
    external = tmp_path / "external"
    external.write_text("untouched", encoding="utf-8")
    (root / ".epistemic-mutation.lock").symlink_to(external)
    with pytest.raises(EpistemicStateError, match="epistemic_mutation_lock_unavailable"):
        with owner._mutation_lock():
            pass
    assert external.read_text(encoding="utf-8") == "untouched"

    (root / ".epistemic-mutation.lock").unlink()
    lock = root / ".epistemic-mutation.lock"
    lock.write_bytes(b"")
    lock.chmod(0o644)
    with pytest.raises(EpistemicStateError, match="epistemic_mutation_lock_invalid"):
        with owner._mutation_lock():
            pass


def test_private_directory_json_inventory_is_bounded(tmp_path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("POSIX descriptor inventory is required")
    root = tmp_path / "records"
    root.mkdir(mode=0o700)
    (root / "one.json").write_text("{}", encoding="utf-8")
    (root / "ignored.tmp").write_text("temporary", encoding="utf-8")
    descriptor = open_private_directory(root, create=False)
    try:
        assert list_bounded_json_names_at(
            descriptor, max_entries=1, max_directory_entries=2) == ("one.json",)
        (root / "overflow.tmp").write_text("temporary", encoding="utf-8")
        with pytest.raises(PrivateFileCustodyError, match="directory_entry_limit_exceeded"):
            list_bounded_json_names_at(
                descriptor, max_entries=1, max_directory_entries=2)
        (root / "overflow.tmp").unlink()
        (root / "two.json").write_text("{}", encoding="utf-8")
        with pytest.raises(PrivateFileCustodyError, match="directory_file_count_limit_exceeded"):
            list_bounded_json_names_at(
                descriptor, max_entries=1, max_directory_entries=3)
    finally:
        import os
        os.close(descriptor)
