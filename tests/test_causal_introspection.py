from __future__ import annotations

import json
import os
from dataclasses import replace

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.causal_introspection import (
    COVERAGE_MANIFEST,
    CausalIntrospectionRuntime,
    CausalReference,
    CaptureContext,
    IntrospectionConfig,
    IntrospectionError,
    MappingMetadataProvider,
    OwnerObservation,
    ProjectionConflict,
    ProviderRegistration,
    SNAPSHOT_DELTA_SCHEMA,
    SemanticTraceDimension,
    build_snapshot_delta,
    build_projection,
    validate_projection,
    verify_snapshot_delta,
    MAX_PROJECTIONS,
    MAX_SNAPSHOT_GENERATIONS,
    MAX_SNAPSHOT_CUSTODY_BYTES,
    _snapshot_capacity_error,
    _digest,
    _snapshot_payload,
    validate_snapshot,
    load_config,
)
from sentientos.world_state_board import WorldStateBoardBuilder


def _reference(owner: str, kind: str = "artifact", suffix: str = "state") -> CausalReference:
    return CausalReference(kind, f"{owner}:{suffix}", "a" * 64, "observed_from", owner)


def _provider(owner: str, domain: str, value=True, *, key="current_posture") -> MappingMetadataProvider:
    ref = _reference(owner)
    return MappingMetadataProvider(
        provider_id=f"provider:{owner}", owner_id=owner, owner_kind=f"{domain}_owner", domain=domain,
        references=(ref,), observations=(OwnerObservation(key, value, "currentness", (ref.reference_id,),
            production_posture="synthetic_test"),),
        semantic_trace={
            "WHO": SemanticTraceDimension((ref.reference_id,), "observed"),
            "WHY": SemanticTraceDimension(), "MAY": SemanticTraceDimension(),
            "WHAT_EXECUTED": SemanticTraceDimension(), "WHAT_IT_COST": SemanticTraceDimension(),
            "WHAT_HAPPENED": SemanticTraceDimension((ref.reference_id,), "observed"),
        })


def _runtime(tmp_path, providers, *, required=()):
    config = IntrospectionConfig(True, tmp_path / "custody", True, 64,
        tuple(item.domain for item in providers), tuple(required))
    return CausalIntrospectionRuntime(config, providers)


def test_common_projection_identity_and_reconstruction(tmp_path):
    registration = ProviderRegistration("serving", "model_serving", _provider("serving", "model_serving"))
    runtime = _runtime(tmp_path, (registration,))
    first = runtime.capture(CaptureContext("tick-1", "revision", "tree", capture_posture="synthetic_test"))
    assert runtime.capture(CaptureContext("tick-1", "revision", "tree", capture_posture="synthetic_test")) == first
    second = runtime.capture(CaptureContext("tick-2", "revision", "tree", capture_posture="synthetic_test"))
    restarted = _runtime(tmp_path, (registration,))
    assert restarted.reconstruct() == (first, second)
    assert second.predecessor_snapshot_digest == first.snapshot_digest


def test_explicit_body_domain_provider_coverage():
    rows = {row["domain"]: row for row in COVERAGE_MANIFEST}
    assert len(rows) == 17
    assert rows["model_serving"]["coverage"] == "implemented"
    assert rows["causal_resources"]["coverage"] == "partial"
    assert all(row["rationale"] for row in rows.values())


def test_three_domain_live_capture_and_next_tick_world_state(tmp_path):
    registrations = tuple(ProviderRegistration(owner, domain, _provider(owner, domain)) for owner, domain in (
        ("serving-owner", "model_serving"),
        ("epistemic-owner", "persistent_epistemics"),
        ("supervisor-owner", "runtime_supervision"),
    ))
    runtime = _runtime(tmp_path, registrations, required=tuple(item.domain for item in registrations))
    captured = runtime.capture(CaptureContext("tick-N", capture_posture="synthetic_test"))
    assert len(captured.projections) == 3
    assert runtime.world_state_records(before_generation=1) == []
    records = runtime.world_state_records(before_generation=2)
    assert {item["source_id"] for item in records} == set(captured.projection_ids)
    assert all(item["source_kind"] == "owner_introspection" for item in records)
    assert all(item["payload"]["introspection_snapshot_id"] == captured.snapshot_id
        and item["payload"]["introspection_snapshot_digest"] == captured.snapshot_digest
        and item["payload"]["introspection_snapshot_generation"] == captured.generation
        and item["payload"]["introspection_snapshot_predecessor_digest"]
            == captured.predecessor_snapshot_digest
        and item["payload"]["introspection_capture_tick"] == captured.capture_tick
        for item in records)
    board = WorldStateBoardBuilder().build(records)
    assert {fact.subject.subject_id for fact in board.facts} == {
        "serving-owner", "epistemic-owner", "supervisor-owner"}
    assert all(fact.payload["authority"] is False and fact.payload["current_truth"] is False for fact in board.facts)


def test_snapshot_delta_binds_external_change_reference_without_claiming_causality(tmp_path):
    provider = _provider("supervisor", "runtime_supervision", value="state-a", key="configuration")
    registration = ProviderRegistration("supervisor", "runtime_supervision", provider)
    runtime = _runtime(tmp_path, (registration,))
    runtime.capture(CaptureContext("tick-1", capture_posture="synthetic_test"))

    intervention = CausalReference(
        "receipt", "operator-change-1", "b" * 64,
        "operator_updated_ruleset", "operator")
    provider._observations = (OwnerObservation(
        "configuration", "state-b", "configuration",
        ("supervisor:state", "operator-change-1"),
        production_posture="synthetic_test"),)
    provider._references = (_reference("supervisor"), intervention)
    runtime.capture(CaptureContext("tick-2", capture_posture="synthetic_test"))

    history = runtime.reconstruct()
    delta = build_snapshot_delta(history)
    verified = verify_snapshot_delta(delta, history)
    owner_change, = delta["owner_changes"]
    assert verified == delta
    assert delta["schema_version"] == SNAPSHOT_DELTA_SCHEMA
    assert owner_change["status"] == "changed"
    assert owner_change["changed_observations"][0]["observation_key"] == "configuration"
    assert "state-a" not in json.dumps(delta)
    assert "state-b" not in json.dumps(delta)
    assert owner_change["changed_references"][0]["reference_id"] == "operator-change-1"
    assert delta["causal_inference_performed"] is False
    assert delta["causal_claim_made"] is False
    assert delta["authority"] is False

    records = runtime.world_state_records(before_generation=3)
    delta_records = [row for row in records if row["source_kind"] == "owner_introspection_delta"]
    assert len(delta_records) == 1
    assert delta_records[0]["payload"]["snapshot_delta_digest"] == delta["delta_digest"]
    assert delta_records[0]["payload"]["owner_change"] == owner_change
    assert delta_records[0]["payload"]["causal_claim_made"] is False

    tampered = dict(delta)
    tampered["causal_claim_made"] = True
    with pytest.raises(IntrospectionError, match="snapshot_delta_mismatch"):
        verify_snapshot_delta(tampered, history)


def test_snapshot_delta_reports_source_generation_change_without_causal_claim(tmp_path):
    provider = _provider("supervisor", "runtime_supervision", value="same", key="status")
    runtime = _runtime(tmp_path, (ProviderRegistration("supervisor", "runtime_supervision", provider),))
    runtime.capture(CaptureContext("tick-1", "commit-a", "tree-a", capture_posture="synthetic_test"))
    runtime.capture(CaptureContext("tick-2", "commit-b", "tree-b", capture_posture="synthetic_test"))

    history = runtime.reconstruct()
    delta = build_snapshot_delta(history)
    change = delta["source_generation_change"]
    assert verify_snapshot_delta(delta, history) == delta
    assert delta["schema_version"] == SNAPSHOT_DELTA_SCHEMA
    assert change == {
        "status": "changed",
        "previous": {"repository_revision": "commit-a", "repository_tree": "tree-a", "available": True},
        "current": {"repository_revision": "commit-b", "repository_tree": "tree-b", "available": True},
        "changed_fields": ["repository_revision", "repository_tree"],
    }
    assert delta["owner_changes"][0]["status"] == "stable"
    assert delta["causal_inference_performed"] is False
    assert delta["causal_claim_made"] is False
    assert delta["authority"] is False

    records = runtime.world_state_records(before_generation=3)
    source_records = [row for row in records
        if row["source_kind"] == "repository_source_generation_delta"]
    assert len(source_records) == 1
    assert source_records[0]["disposition"] == "source_generation_changed"
    assert source_records[0]["payload"]["source_generation_change"] == change
    assert source_records[0]["payload"]["causal_claim_made"] is False
    assert source_records[0]["payload"]["authority"] is False

    tampered = dict(delta)
    tampered["source_generation_change"] = dict(change, status="stable")
    with pytest.raises(IntrospectionError, match="snapshot_delta_mismatch"):
        verify_snapshot_delta(tampered, history)


def test_snapshot_delta_marks_source_generation_unavailable_and_records_availability_loss(tmp_path):
    provider = _provider("supervisor", "runtime_supervision", value="same", key="status")
    runtime = _runtime(tmp_path, (ProviderRegistration("supervisor", "runtime_supervision", provider),))
    runtime.capture(CaptureContext("tick-1", "commit-a", "tree-a", capture_posture="synthetic_test"))
    runtime.capture(CaptureContext("tick-2", capture_posture="synthetic_test"))

    history = runtime.reconstruct()
    delta = build_snapshot_delta(history)
    change = delta["source_generation_change"]
    assert change["status"] == "unavailable"
    assert change["previous"]["available"] is True
    assert change["current"] == {
        "repository_revision": None, "repository_tree": None, "available": False,
    }
    records = runtime.world_state_records(before_generation=3)
    source_record, = [row for row in records
        if row["source_kind"] == "repository_source_generation_delta"]
    assert source_record["disposition"] == "source_generation_identity_became_unavailable"
    assert source_record["payload"]["source_generation_change"] == change


def test_snapshot_delta_reports_stable_source_generation_and_suppresses_repeated_unknown_records(tmp_path):
    provider = _provider("supervisor", "runtime_supervision", value="same", key="status")
    runtime = _runtime(tmp_path, (ProviderRegistration("supervisor", "runtime_supervision", provider),))
    runtime.capture(CaptureContext("tick-1", "commit-a", "tree-a", capture_posture="synthetic_test"))
    runtime.capture(CaptureContext("tick-2", "commit-a", "tree-a", capture_posture="synthetic_test"))
    known_delta = build_snapshot_delta(runtime.reconstruct())
    assert known_delta["source_generation_change"]["status"] == "stable"
    assert not any(row["source_kind"] == "repository_source_generation_delta"
                   for row in runtime.world_state_records(before_generation=3))

    runtime.capture(CaptureContext("tick-3", capture_posture="synthetic_test"))
    unknown_delta = build_snapshot_delta(runtime.reconstruct())
    assert unknown_delta["source_generation_change"]["status"] == "unavailable"
    assert any(row["source_kind"] == "repository_source_generation_delta"
               and row["disposition"] == "source_generation_identity_became_unavailable"
               for row in runtime.world_state_records(before_generation=4))

    runtime.capture(CaptureContext("tick-4", capture_posture="synthetic_test"))
    repeated_unknown_delta = build_snapshot_delta(runtime.reconstruct())
    assert repeated_unknown_delta["source_generation_change"]["status"] == "unavailable"
    assert not any(row["source_kind"] == "repository_source_generation_delta"
                   for row in runtime.world_state_records(before_generation=5))


def test_snapshot_delta_ignores_capture_tick_identity_and_marks_failed_owner_unobserved(tmp_path):
    class ToggleProvider(MappingMetadataProvider):
        fail = False

        def project(self, context):
            if self.fail:
                raise RuntimeError("injected provider outage")
            return super().project(context)

    original = _provider("supervisor", "runtime_supervision", value="same", key="status")
    provider = ToggleProvider(
        provider_id=original.provider_id, owner_id=original._owner_id,
        owner_kind=original._owner_kind, domain=original._domain,
        observations=original._observations, references=original._references,
        semantic_trace=original._semantic_trace)
    runtime = _runtime(tmp_path, (ProviderRegistration(
        "supervisor", "runtime_supervision", provider),))

    runtime.capture(CaptureContext("tick-1", capture_posture="synthetic_test"))
    runtime.capture(CaptureContext("tick-2", capture_posture="synthetic_test"))
    stable_delta = build_snapshot_delta(runtime.reconstruct())
    assert stable_delta["owner_changes"][0]["status"] == "stable"
    assert not any(row["source_kind"] == "owner_introspection_delta"
                   for row in runtime.world_state_records(before_generation=3))

    provider.fail = True
    runtime.capture(CaptureContext("tick-3", capture_posture="synthetic_test"))
    history = runtime.reconstruct()
    unavailable_delta = build_snapshot_delta(history)
    assert unavailable_delta["owner_changes"][0]["status"] == "unavailable_in_current_capture"
    records = runtime.world_state_records(before_generation=4)
    delta_records = [row for row in records if row["source_kind"] == "owner_introspection_delta"]
    assert len(delta_records) == 1
    assert delta_records[0]["disposition"] == "unavailable_in_current_capture"

    with pytest.raises(IntrospectionError, match="predecessor_mismatch"):
        build_snapshot_delta((history[0], history[2]))


@pytest.mark.parametrize(("domain", "source_key", "forbidden_key"), (
    ("installation", "provisioned", "commissioned"),
    ("model_supply", "commissioned", "activated"),
    ("model_supply", "activated", "served"),
    ("model_serving", "serving_current", "inference"),
    ("authority_admission", "definition_present", "grant"),
    ("authority_admission", "grant_reference", "admission"),
    ("authority_admission", "admission_reference", "execution"),
    ("effects", "execution_reference", "validated_consequence"),
    ("effects", "readiness", "effect_proven"),
    ("effects", "effect_claimed", "effect_proven"),
    ("canonical_memory", "record_count", "current_truth"),
    ("longitudinal_self_model", "claim_count", "persistent_identity"),
    ("persistent_epistemics", "state_count", "current_truth"),
    ("developmental_history", "record_count", "learning"),
    ("causal_resources", "principal_observed", "cpu_allocation"),
    ("embodiment", "renderer_reported", "independently_observed"),
    ("federation", "candidate_received", "local_adoption"),
    ("runtime_supervision", "service_health", "authority"),
))
def test_body_wide_causal_boundary_table(domain, source_key, forbidden_key):
    provider = _provider(f"{domain}-owner", domain, key=source_key)
    projection = provider.project(CaptureContext("tick", capture_posture="synthetic_test"))
    assert source_key in {item.observation_key for item in projection.observations}
    assert forbidden_key not in {item.observation_key for item in projection.observations}
    assert projection.posture.current_truth is False and projection.posture.authority is False


def test_conflict_is_preserved_without_winner(tmp_path):
    regs = (
        ProviderRegistration("a", "model_serving", _provider("a", "model_serving", True, key="shared.test.key")),
        ProviderRegistration("b", "runtime_supervision", _provider("b", "runtime_supervision", False, key="shared.test.key")),
    )
    runtime = _runtime(tmp_path, regs)
    snapshot = runtime.capture(CaptureContext("tick", capture_posture="synthetic_test"))
    assert snapshot.conflicts[0].observation_key == "shared.test.key"
    assert len(snapshot.conflicts[0].projection_ids) == 2
    assert [item.bounded_value for projection in snapshot.projections for item in projection.observations] == [True, False]
    diagnostic, = [row for row in runtime.world_state_records(before_generation=2)
        if row["subject_kind"] == "snapshot_diagnostics"]
    assert diagnostic["observed_at"] == "tick"
    assert diagnostic["payload"]["conflicts"] == [{
        "observation_key": "shared.test.key",
        "projection_ids": list(snapshot.conflicts[0].projection_ids),
    }]
    assert diagnostic["payload"]["conflict_posture"] == "unresolved_no_winner_selected"
    assert diagnostic["payload"]["authority"] is False
    assert diagnostic["effect_claimed"] is False and diagnostic["effect_proven"] is False


def test_snapshot_validation_recomputes_completion_and_conflict_claims(tmp_path):
    class Broken:
        provider_id = "broken"
        def project(self, context):
            raise RuntimeError("discarded")

    partial_runtime = _runtime(tmp_path / "partial", (
        ProviderRegistration("good", "model_serving", _provider("good", "model_serving")),
        ProviderRegistration("bad", "runtime_supervision", Broken()),
    ))
    partial = partial_runtime.capture(CaptureContext("tick", capture_posture="synthetic_test"))
    forged_complete = replace(partial, completion_posture="complete", snapshot_id="", snapshot_digest="")
    digest = _digest(_snapshot_payload(forged_complete))
    forged_complete = replace(forged_complete,
        snapshot_id=f"causal-introspection-{digest[:20]}", snapshot_digest=digest)
    with pytest.raises(IntrospectionError, match="completion_posture"):
        validate_snapshot(forged_complete)

    complete_runtime = _runtime(tmp_path / "complete", (
        ProviderRegistration("owner", "model_serving", _provider("owner", "model_serving")),
    ))
    complete = complete_runtime.capture(CaptureContext("other-tick", capture_posture="synthetic_test"))
    forged_conflict = replace(complete,
        conflicts=(ProjectionConflict("invented.conflict", ("unregistered-projection",)),),
        snapshot_id="", snapshot_digest="")
    digest = _digest(_snapshot_payload(forged_conflict))
    forged_conflict = replace(forged_conflict,
        snapshot_id=f"causal-introspection-{digest[:20]}", snapshot_digest=digest)
    with pytest.raises(IntrospectionError, match="conflict_inventory"):
        validate_snapshot(forged_conflict)


def test_snapshot_validation_rejects_duplicate_owner_projection_after_redigest(tmp_path):
    registration = ProviderRegistration("serving", "model_serving", _provider("serving", "model_serving"))
    original = _runtime(tmp_path, (registration,)).capture(
        CaptureContext("tick", capture_posture="synthetic_test"))
    projection = original.projections[0]
    forged = replace(original, snapshot_id="", snapshot_digest="",
        projection_ids=(projection.projection_id, projection.projection_id),
        projection_digests=(projection.projection_digest, projection.projection_digest),
        projections=(projection, projection))
    digest = _digest(_snapshot_payload(forged))
    forged = replace(forged, snapshot_id=f"causal-introspection-{digest[:20]}",
        snapshot_digest=digest)

    with pytest.raises(IntrospectionError, match="snapshot_projection_identity_not_unique"):
        validate_snapshot(forged)


def test_projection_and_registration_require_attributable_owner_identity(tmp_path):
    with pytest.raises(IntrospectionError, match="owner_identity_required"):
        build_projection(owner_id="", owner_kind="model_serving_owner", domain="model_serving",
            context=CaptureContext("tick"), source_references=(), causal_references=(),
            observations=())

    provider = MappingMetadataProvider(provider_id="provider", owner_id="",
        owner_kind="model_serving_owner", domain="model_serving", observations=())
    with pytest.raises(IntrospectionError, match="provider_registration_identity_required"):
        _runtime(tmp_path, (ProviderRegistration("", "model_serving", provider),))


def test_capture_and_projection_require_nonempty_temporal_identity(tmp_path):
    registration = ProviderRegistration("serving", "model_serving", _provider("serving", "model_serving"))
    runtime = _runtime(tmp_path, (registration,))
    with pytest.raises(IntrospectionError, match="capture_tick_required"):
        runtime.capture(CaptureContext("", capture_posture="synthetic_test"))

    with pytest.raises(IntrospectionError, match="capture_tick_required"):
        build_projection(owner_id="serving", owner_kind="serving_owner", domain="model_serving",
            context=CaptureContext(""), source_references=(), causal_references=(),
            observations=())


def test_stale_provider_projection_is_retained_as_capture_failure(tmp_path):
    class Stale:
        provider_id = "stale"
        def project(self, context):
            stale_context = CaptureContext("older-tick", capture_posture=context.capture_posture)
            return _provider("stale", "model_serving").project(stale_context)

    runtime = _runtime(tmp_path, (
        ProviderRegistration("stale", "model_serving", Stale()),
    ))
    snapshot = runtime.capture(CaptureContext("current-tick", capture_posture="synthetic_test"))
    assert snapshot.capture_tick == "current-tick"
    assert snapshot.projections == ()
    assert snapshot.completion_posture == "partial"
    assert len(snapshot.capture_findings) == 1
    assert snapshot.capture_findings[0].error_code == "provider_projection_failed"
    assert snapshot.capture_findings[0].error_class == "IntrospectionError"
    assert runtime.world_state_records(before_generation=2)[0]["subject_kind"] == "snapshot_diagnostics"


def test_partial_capture_preserves_successful_projection(tmp_path):
    class Broken:
        provider_id = "broken"
        def project(self, context):
            raise RuntimeError("sensitive traceback detail")
    regs = (ProviderRegistration("good", "model_serving", _provider("good", "model_serving")),
            ProviderRegistration("bad", "runtime_supervision", Broken()))
    runtime = _runtime(tmp_path, regs, required=("model_serving", "runtime_supervision"))
    snapshot = runtime.capture(CaptureContext("tick", capture_posture="synthetic_test"))
    assert snapshot.completion_posture == "partial"
    assert [item.owner_id for item in snapshot.projections] == ["good"]
    serialized = json.dumps(snapshot, default=lambda value: value.__dict__)
    assert "sensitive traceback detail" not in serialized
    diagnostic, = [row for row in runtime.world_state_records(before_generation=2)
        if row["subject_kind"] == "snapshot_diagnostics"]
    assert diagnostic["disposition"] == "incomplete"
    assert diagnostic["payload"]["snapshot_completion_posture"] == "partial"
    assert diagnostic["payload"]["capture_findings"][:1] == [{
        "owner_id": "bad", "domain": "runtime_supervision",
        "error_code": "provider_projection_failed", "error_class": "RuntimeError",
    }]
    assert diagnostic["payload"]["capture_findings"][1]["error_code"] == "required_provider_missing"
    assert "sensitive traceback detail" not in json.dumps(diagnostic)


def test_memory_privacy_and_resource_unknown_are_preserved(tmp_path):
    sensitive = "recognizable-private-fixture-text"
    memory = MappingMetadataProvider(provider_id="memory-provider", owner_id="memory", owner_kind="memory_owner",
        domain="canonical_memory", references=(_reference("memory", "memory_custody"),),
        observations=(OwnerObservation("record_count", 1, "count", production_posture="synthetic_test"),
                      OwnerObservation("receipt_ids", ["receipt-1"], "identity", production_posture="synthetic_test")))
    resource = _provider("resource", "causal_resources", key="principal_observed")
    snapshot = _runtime(tmp_path, (ProviderRegistration("memory", "canonical_memory", memory),
        ProviderRegistration("resource", "causal_resources", resource))).capture(
            CaptureContext("tick", capture_posture="synthetic_test"))
    payload = (tmp_path / "custody" / "generation-00000000000000000001.json").read_text()
    assert sensitive not in payload
    assert not any("allocation" in item.observation_key for projection in snapshot.projections for item in projection.observations)


def test_authority_truth_production_effect_and_credentials_rejected():
    base = _provider("owner", "effects").project(CaptureContext("tick", capture_posture="synthetic_test"))
    with pytest.raises(IntrospectionError, match="authority"):
        validate_projection(replace(base, posture=replace(base.posture, authority=True)))
    current_truth = replace(base, posture=replace(base.posture, current_truth=True))
    with pytest.raises(IntrospectionError, match="authority"):
        validate_projection(current_truth)
    with pytest.raises(IntrospectionError, match="production"):
        build_projection(owner_id="owner", owner_kind="effects_owner", domain="effects",
            context=CaptureContext("tick", capture_posture="synthetic_test"), source_references=(), causal_references=(),
            observations=(OwnerObservation("posture", True, "currentness", production_posture="production"),))
    with pytest.raises(IntrospectionError, match="effect_proof"):
        build_projection(owner_id="owner", owner_kind="effects_owner", domain="effects",
            context=CaptureContext("tick"), source_references=(), causal_references=(),
            observations=(OwnerObservation("effect_proven", True, "effect_evidence"),))
    with pytest.raises(IntrospectionError, match="credential"):
        build_projection(owner_id="owner", owner_kind="effects_owner", domain="effects",
            context=CaptureContext("tick"), source_references=(), causal_references=(),
            observations=(OwnerObservation("api_key", "not-a-real-key", "configuration"),))


def test_provider_purity_and_recursive_provider_rejected(tmp_path):
    provider = _provider("owner", "model_serving")
    before = provider.__dict__.copy()
    provider.project(CaptureContext("tick", capture_posture="synthetic_test"))
    assert provider.__dict__ == before
    runtime = _runtime(tmp_path, (ProviderRegistration("owner", "model_serving", provider),))
    with pytest.raises(IntrospectionError, match="recursive"):
        CausalIntrospectionRuntime(runtime.config,
            (ProviderRegistration("causal_introspection_runtime", "model_serving", runtime),))


def test_tamper_and_same_tick_change_fail_closed(tmp_path):
    registration = ProviderRegistration("owner", "model_serving", _provider("owner", "model_serving"))
    runtime = _runtime(tmp_path, (registration,))
    runtime.capture(CaptureContext("tick", capture_posture="synthetic_test"))
    changed = ProviderRegistration("owner", "model_serving", _provider("owner", "model_serving", False))
    with pytest.raises(IntrospectionError, match="same_tick"):
        _runtime(tmp_path, (changed,)).capture(CaptureContext("tick", capture_posture="synthetic_test"))
    path = tmp_path / "custody" / "generation-00000000000000000001.json"
    payload = json.loads(path.read_text())
    payload["projections"][0]["owner_id"] = "tampered"
    path.write_text(json.dumps(payload))
    with pytest.raises(IntrospectionError):
        runtime.reconstruct()


def test_model_transition_preserves_introspection_chain(tmp_path):
    model_a = ProviderRegistration("serving", "model_serving",
        _provider("serving", "model_serving", "model-A", key="loaded_model_ref"))
    first = _runtime(tmp_path, (model_a,)).capture(
        CaptureContext("tick-A", capture_posture="synthetic_test"))
    model_b = ProviderRegistration("serving", "model_serving",
        _provider("serving", "model_serving", "model-B", key="loaded_model_ref"))
    second = _runtime(tmp_path, (model_b,)).capture(
        CaptureContext("tick-B", capture_posture="synthetic_test"))
    assert second.generation == 2
    assert second.predecessor_snapshot_digest == first.snapshot_digest
    assert first.projections[0].observations[0].bounded_value == "model-A"
    assert second.projections[0].observations[0].bounded_value == "model-B"


def test_orphaned_stage_blocks_new_capture_without_hiding_committed_history(tmp_path):
    registration = ProviderRegistration("serving", "model_serving", _provider("serving", "model_serving"))
    runtime = _runtime(tmp_path, (registration,))
    committed = runtime.capture(CaptureContext("tick-1", capture_posture="synthetic_test"))
    staging = runtime.config.custody_root / ".causal-introspection-interrupted.tmp"
    staging.write_bytes(b"partial unpublished capture")

    assert runtime.reconstruct() == (committed,)
    with pytest.raises(IntrospectionError, match="snapshot_staging_recovery_required"):
        runtime.capture(CaptureContext("tick-2", capture_posture="synthetic_test"))


def test_append_capacity_preflight_matches_reconstruction_limits():
    assert _snapshot_capacity_error(MAX_SNAPSHOT_GENERATIONS - 1,
        MAX_SNAPSHOT_CUSTODY_BYTES - 8, 8) is None
    assert _snapshot_capacity_error(MAX_SNAPSHOT_GENERATIONS,
        MAX_SNAPSHOT_CUSTODY_BYTES - 8, 1) == "snapshot_generation_limit_exceeded"
    assert _snapshot_capacity_error(MAX_SNAPSHOT_GENERATIONS - 1,
        MAX_SNAPSHOT_CUSTODY_BYTES - 8, 9) == "snapshot_custody_limit_exceeded"
    assert _snapshot_capacity_error(0, 0, 0) is None


def test_observation_source_refs_must_resolve_to_inventory():
    ref = _reference("serving")
    with pytest.raises(IntrospectionError, match="observation_source_reference_unresolved"):
        build_projection(owner_id="serving", owner_kind="serving_owner", domain="model_serving",
            context=CaptureContext("tick", capture_posture="synthetic_test"),
            source_references=(ref,), causal_references=(),
            observations=(OwnerObservation("session_id", "session-1", "identity",
                source_refs=("unlisted-reference",), production_posture="synthetic_test"),))


def test_projection_rejects_duplicate_reference_identity():
    first = CausalReference("artifact", "shared", "a" * 64, "observed_from", "owner-a")
    second = CausalReference("artifact", "shared", "b" * 64, "derived_from", "owner-b")

    with pytest.raises(IntrospectionError, match="duplicate_causal_reference_id"):
        build_projection(owner_id="serving", owner_kind="serving_owner", domain="model_serving",
            context=CaptureContext("tick", capture_posture="synthetic_test"),
            source_references=(first,), causal_references=(second,),
            observations=(OwnerObservation("loaded_model_ref", "model-A", "identity",
                source_refs=("shared",), production_posture="synthetic_test"),))


def test_projection_rejects_malformed_causal_reference_identity_fields():
    valid = _reference("owner")
    malformed = (
        replace(valid, reference_kind=[]),
        replace(valid, reference_id=""),
        replace(valid, reference_digest="not-a-digest"),
        replace(valid, relation=""),
        replace(valid, source_owner_id=""),
        replace(valid, schema_version="foreign-schema"),
    )

    for reference in malformed:
        with pytest.raises(IntrospectionError, match="invalid_causal_reference"):
            build_projection(owner_id="owner", owner_kind="serving_owner", domain="model_serving",
                context=CaptureContext("tick", capture_posture="synthetic_test"),
                source_references=(reference,), causal_references=(), observations=())


def test_projection_rejects_whitespace_only_causal_identity_fields():
    valid = _reference("owner")
    for field in ("reference_id", "relation", "source_owner_id"):
        reference = replace(valid, **{field: " \t "})
        with pytest.raises(IntrospectionError, match="invalid_causal_reference"):
            build_projection(owner_id="owner", owner_kind="serving_owner", domain="model_serving",
                context=CaptureContext("tick", capture_posture="synthetic_test"),
                source_references=(reference,), causal_references=(), observations=())

    for owner_id, owner_kind, tick, expected in (
        (" \t ", "serving_owner", "tick", "owner_identity_required"),
        ("owner", " \t ", "tick", "owner_identity_required"),
        ("owner", "serving_owner", " \t ", "capture_tick_required"),
    ):
        with pytest.raises(IntrospectionError, match=expected):
            build_projection(owner_id=owner_id, owner_kind=owner_kind,
                domain="model_serving", context=CaptureContext(tick, capture_posture="synthetic_test"),
                source_references=(), causal_references=(), observations=())


def test_runtime_constructor_enforces_loaded_configuration_bounds(tmp_path):
    provider = _provider("owner", "model_serving")
    oversized = IntrospectionConfig(True, tmp_path / "custody", True,
        MAX_PROJECTIONS + 1, ("model_serving",), ())
    with pytest.raises(IntrospectionError, match="invalid_max_projections"):
        CausalIntrospectionRuntime(oversized, ())

    unselected_required = IntrospectionConfig(True, tmp_path / "custody", True,
        1, ("model_serving",), ("effects",))
    with pytest.raises(IntrospectionError, match="invalid_config_domains"):
        CausalIntrospectionRuntime(unselected_required, (
            ProviderRegistration("owner", "model_serving", provider),))


def test_group_or_world_writable_custody_root_is_rejected_on_posix(tmp_path):
    import os
    if os.name != "posix":
        pytest.skip("POSIX directory mode contract")
    registration = ProviderRegistration("owner", "model_serving", _provider("owner", "model_serving"))
    runtime = _runtime(tmp_path, (registration,))
    runtime.config.custody_root.mkdir(mode=0o700)
    runtime.config.custody_root.chmod(0o770)
    with pytest.raises(IntrospectionError, match="custody_root_writable_by_other_users"):
        runtime.reconstruct()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-relative custody is POSIX-only")
def test_custody_root_rejects_symlinked_ancestor(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    runtime = _runtime(tmp_path, ())
    runtime.config = replace(runtime.config, custody_root=alias / "custody")

    with pytest.raises(IntrospectionError, match="custody_root_invalid"):
        runtime.capture(CaptureContext("tick", capture_posture="synthetic_test"))

    assert not (target / "custody").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-relative config reads are POSIX-only")
def test_config_rejects_symlinked_parent_directory(tmp_path):
    from sentientos.causal_introspection import SCHEMA_VERSION

    real = tmp_path / "real"
    real.mkdir()
    config = real / "config.json"
    config.write_text(json.dumps({
        "schema": SCHEMA_VERSION, "enabled": True,
        "custody_root": str(real / "custody"),
        "world_state_consumption_enabled": False,
        "enabled_domains": [], "required_domains": [],
    }))
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(IntrospectionError, match="configuration_unavailable_or_invalid"):
        load_config(alias / config.name)


def test_reconstruction_rejects_canonical_unknown_snapshot_fields(tmp_path):
    registration = ProviderRegistration("serving", "model_serving", _provider("serving", "model_serving"))
    runtime = _runtime(tmp_path, (registration,))
    runtime.capture(CaptureContext("tick-1", capture_posture="synthetic_test"))
    path = tmp_path / "custody" / "generation-00000000000000000001.json"
    payload = json.loads(path.read_text())
    payload["unrecognized_custody_field"] = "must not be silently discarded"
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))

    with pytest.raises(IntrospectionError, match="snapshot_noncanonical"):
        runtime.reconstruct()
