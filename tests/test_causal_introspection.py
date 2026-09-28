from __future__ import annotations

import json
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
    ProviderRegistration,
    SemanticTraceDimension,
    build_projection,
    validate_projection,
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
    board = WorldStateBoardBuilder().build(records)
    assert {fact.subject.subject_id for fact in board.facts} == {
        "serving-owner", "epistemic-owner", "supervisor-owner"}
    assert all(fact.payload["authority"] is False and fact.payload["current_truth"] is False for fact in board.facts)


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
    snapshot = _runtime(tmp_path, regs).capture(CaptureContext("tick", capture_posture="synthetic_test"))
    assert snapshot.conflicts[0].observation_key == "shared.test.key"
    assert len(snapshot.conflicts[0].projection_ids) == 2
    assert [item.bounded_value for projection in snapshot.projections for item in projection.observations] == [True, False]


def test_partial_capture_preserves_successful_projection(tmp_path):
    class Broken:
        provider_id = "broken"
        def project(self, context):
            raise RuntimeError("sensitive traceback detail")
    regs = (ProviderRegistration("good", "model_serving", _provider("good", "model_serving")),
            ProviderRegistration("bad", "runtime_supervision", Broken()))
    snapshot = _runtime(tmp_path, regs, required=("model_serving", "runtime_supervision")).capture(
        CaptureContext("tick", capture_posture="synthetic_test"))
    assert snapshot.completion_posture == "partial"
    assert [item.owner_id for item in snapshot.projections] == ["good"]
    serialized = json.dumps(snapshot, default=lambda value: value.__dict__)
    assert "sensitive traceback detail" not in serialized


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
