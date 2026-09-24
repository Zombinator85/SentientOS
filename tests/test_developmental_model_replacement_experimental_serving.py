from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.developmental_model_replacement_experiment import (
    CognitiveModelIdentity, FrozenCausalContext, ModelDevelopmentProvenance,
    ModelReplacementArtifactStore, ModelReplacementProtocol,
)
from sentientos.developmental_model_replacement_experimental_serving import (
    APPROVAL_SCHEMA, EFFECTS, ExperimentalModelServingError, approval_bindings,
    effect_set_digest, verify_runtime_approval,
)
from sentientos.local_runtime_provisioning import semantic_digest

pytestmark = pytest.mark.no_legacy_skip


def identity(name: str) -> CognitiveModelIdentity:
    observed = {"engine":"llama_cpp", "resolved_artifact_path":f"/models/{name}.gguf",
        "semantic_artifact_identity":f"sha256:{name*8}", "model_content_sha256":name*8,
        "artifact_size_bytes":8, "sidecar_metadata_digest":None, "configuration_digest":f"cfg-{name}",
        "candidate_index":0, "posture":"production", "fallback":False}
    from sentientos.developmental_model_replacement_experiment import _digest
    return CognitiveModelIdentity.create(model_id=f"model-{name}", semantic_artifact_identity=observed["semantic_artifact_identity"],
        model_content_sha256=observed["model_content_sha256"], artifact_size_bytes=8, sidecar_metadata_digest=None,
        configuration_digest=observed["configuration_digest"], engine_runtime_family="llama_cpp", candidate_index=0,
        active_production=True, fallback=False, authority_record_id=f"record-{name}", authority_record_digest=f"digest-{name}",
        active_model_identity=observed, active_model_identity_digest=_digest(observed))


def protocol() -> ModelReplacementProtocol:
    context = FrozenCausalContext.create(snapshot_id="s", snapshot_digest="sd", current_projection_id="p",
        current_projection_digest="pd", current_fact_ids=(), projected_content_digest="sha256:" + "0"*64,
        current_projection_payload={}, history_record_ids=(), history_record_digests=(),
        history_record_set_digest="sha256:" + "0"*64, history_projection_payload=(), instruction_template="i",
        instruction_template_digest="sha256:" + "0"*64, inference_budget={}, generation_posture={"temperature":0},
        repository_generation_identity=None)
    # Only protocol verification matters here; avoid unrelated context content verification.
    a, b = identity("a"), identity("b")
    return ModelReplacementProtocol.create(context, a, b, ModelDevelopmentProvenance.create(a), ModelDevelopmentProvenance.create(b))


def test_preregistration_before_load_verified_loader(tmp_path: Path) -> None:
    item = protocol(); store = ModelReplacementArtifactStore(tmp_path)
    with pytest.raises(Exception): store.load_verified_protocol(item.protocol_id, item.protocol_digest)
    store.persist_protocol(item)
    assert store.load_verified_protocol(item.protocol_id, item.protocol_digest) == item


def test_tampered_preregistered_protocol_fails(tmp_path: Path) -> None:
    item = protocol(); store = ModelReplacementArtifactStore(tmp_path); store.persist_protocol(item)
    path = store.protocols / f"{item.protocol_id}.json"; path.write_text("{}")
    with pytest.raises(Exception): store.load_verified_protocol(item.protocol_id, item.protocol_digest)


def approval(intent: dict[str, object]) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    value = {"schema_version":APPROVAL_SCHEMA, "approval_status":"approved", "approval_evidence_id":"approval-1",
        "operator_identity":"operator-1", "evidence_source":"signed-local-evidence", "evidence_provenance":"operator-console",
        "approval_timestamp":now.isoformat(), "not_before":(now-timedelta(seconds=1)).isoformat(),
        "expires_at":(now+timedelta(minutes=5)).isoformat(), "synthetic_test_evidence":True, **approval_bindings(intent)}
    value["approval_digest"] = semantic_digest(value)
    return value


def intent() -> dict[str, object]:
    value = {"target_capability":"developmental_model_replacement_experimental_serving",
        "target_principal":"deterministic_developmental_model_replacement_experimental_serving_controller",
        "effects":sorted(EFFECTS), "effect_set_digest":effect_set_digest(), "installation_identity":"installation-1",
        "protocol_id":"model-replacement-protocol-x", "protocol_digest":"sha256:x", "model_role":"model_a",
        "expected_model_identity_digest":"sha256:i", "commissioning_receipt_id":"commissioning-receipt-x",
        "commissioning_receipt_digest":"x", "artifact_sha256":"a", "artifact_size_bytes":1, "runtime_id":"r",
        "interpreter_path":"/python", "load_configuration":{"n_ctx":1,"n_gpu_layers":0}, "correlation_id":"correlation-1",
        "intent_id":"experimental-serving-intent-x", "intent_digest":"x"}
    return value


def test_operator_approval_precedes_load_and_is_exact() -> None:
    target = intent(); evidence = approval(target)
    assert verify_runtime_approval(evidence, target, observation_time=datetime.now(timezone.utc),
        allow_synthetic_for_tests=True)["operator_identity"] == "operator-1"
    altered = dict(evidence); altered["operator_identity"] = "other"
    with pytest.raises(ExperimentalModelServingError): verify_runtime_approval(altered, target,
        observation_time=datetime.now(timezone.utc), allow_synthetic_for_tests=True)


def test_synthetic_vs_production_evidence_posture() -> None:
    target = intent(); evidence = approval(target)
    with pytest.raises(ExperimentalModelServingError, match="synthetic_approval_forbidden"):
        verify_runtime_approval(evidence, target, observation_time=datetime.now(timezone.utc))


def test_runtime_schemas_and_effect_surface_are_exact() -> None:
    assert len(EFFECTS) == 8
    assert effect_set_digest() == semantic_digest({"effects": sorted(EFFECTS)})
