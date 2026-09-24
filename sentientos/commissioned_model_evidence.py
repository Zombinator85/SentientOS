"""Read-only verification and identity projection for commissioned local models."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from .developmental_model_replacement_experiment import CognitiveModelIdentity
from .installation_state import InstallationStateError, InstallationStateHandle
from .local_model_authority import digest_payload
from .local_model_catalog_consumer_custody import construct_authoritative_catalog_consumer_proof
from .local_model_production_commissioning_authority import verify_hardened_receipt


class CommissionedModelEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedCommissionedModel:
    receipt: Mapping[str, Any]
    catalog_proof: Mapping[str, Any]
    artifact_path: str
    artifact_sha256: str
    artifact_size_bytes: int
    cognitive_identity: CognitiveModelIdentity


def _digest(value: Any) -> str:
    return "sha256:" + cast(str, digest_payload(value))


def _read_artifact(receipt: Mapping[str, Any]) -> tuple[str, str, int]:
    identity = receipt.get("observed_active_model_identity")
    if not isinstance(identity, Mapping):
        raise CommissionedModelEvidenceError("commissioned_artifact_identity_missing")
    raw = identity.get("resolved_artifact_path") or identity.get("model_path") or identity.get("path")
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        raise CommissionedModelEvidenceError("commissioned_artifact_path_invalid")
    path = Path(raw)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path:
            raise CommissionedModelEvidenceError("commissioned_artifact_path_unsafe")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        digest, size = hashlib.sha256(), 0
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise CommissionedModelEvidenceError("commissioned_artifact_path_unsafe")
            while block := os.read(fd, 1024 * 1024):
                digest.update(block); size += len(block)
        finally:
            os.close(fd)
    except OSError as exc:
        raise CommissionedModelEvidenceError("commissioned_artifact_unavailable") from exc
    if digest.hexdigest() != receipt.get("artifact_sha256") or size != receipt.get("artifact_size_bytes"):
        raise CommissionedModelEvidenceError("commissioned_artifact_stale")
    if identity.get("model_content_sha256") not in {None, digest.hexdigest()} or identity.get("artifact_size_bytes") not in {None, size}:
        raise CommissionedModelEvidenceError("commissioned_artifact_identity_mismatch")
    return str(path), digest.hexdigest(), size


def verify_commissioned_model(handle: InstallationStateHandle, receipt_id: str, *,
                              allow_synthetic_for_tests: bool = False) -> VerifiedCommissionedModel:
    """Verify v3 receipt custody, catalog provenance, artifact bytes, and project identity.

    ``authority_record_digest`` is the SHA-256-prefixed digest of the exact semantic
    authority-record payload: model id, authority-map digest, and observed active
    identity.  Its deterministic id is the first 24 hex digits of that digest.
    """
    if not receipt_id.startswith("commissioning-receipt-") or "/" in receipt_id or "\\" in receipt_id:
        raise CommissionedModelEvidenceError("commissioning_receipt_id_invalid")
    try:
        raw = handle.read_regular(handle.fixed_object(f"local-model/commissioning/receipts/{receipt_id}.json"))
        receipt = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, InstallationStateError) as exc:
        raise CommissionedModelEvidenceError("commissioning_receipt_not_in_canonical_custody") from exc
    if (not isinstance(receipt, dict) or receipt.get("receipt_id") != receipt_id
            or not verify_hardened_receipt(receipt, allow_synthetic_for_tests=allow_synthetic_for_tests)):
        raise CommissionedModelEvidenceError("hardened_commissioning_receipt_v3_required")
    required = ("commissioning_intent_id", "commissioning_intent_digest", "commissioning_plan_digest",
                "external_approval_evidence_id", "external_approval_semantic_digest",
                "hardened_acquisition_plan_digest", "hardened_acquisition_receipt_identity",
                "hardened_acquisition_receipt_digest", "model_commissioning_admission_ref",
                "smoke_local_model_inference_admission_ref", "smoke_receipt_digest",
                "observed_active_model_identity", "authority_map_digest", "load_configuration")
    if any(key not in receipt for key in required):
        raise CommissionedModelEvidenceError("commissioning_lineage_incomplete")
    if (receipt.get("admission_outcome") != "allow" or receipt.get("control_plane_authority_class") != "model_commissioning"
            or receipt.get("model_left_loaded") is not False or receipt.get("activated") is not False
            or receipt.get("serving_authority_granted") is not False):
        raise CommissionedModelEvidenceError("commissioning_lineage_invalid")
    proof = dict(construct_authoritative_catalog_consumer_proof(handle).proof)
    expected = {"installation_identity": receipt.get("installation_identity"),
                "custody_identity": receipt.get("catalog_custody_identity"),
                "authoritative_catalog_semantic_digest": receipt.get("current_authoritative_catalog_digest"),
                "proof_semantic_digest": receipt.get("current_authoritative_proof_digest"),
                "deployment_receipt_id": receipt.get("deployment_receipt_id"),
                "deployment_receipt_semantic_digest": receipt.get("deployment_receipt_semantic_digest")}
    if any(proof.get(key) != value for key, value in expected.items()):
        raise CommissionedModelEvidenceError("commissioning_catalog_provenance_stale")
    path, sha256, size = _read_artifact(receipt)
    observed = dict(receipt["observed_active_model_identity"])
    authority_payload = {"model_id": receipt["model_id"], "authority_map_digest": receipt["authority_map_digest"],
                         "observed_active_model_identity": observed}
    authority_digest = _digest(authority_payload)
    identity = CognitiveModelIdentity.create(
        model_id=str(receipt["model_id"]),
        semantic_artifact_identity=str(observed["semantic_artifact_identity"]),
        model_content_sha256=sha256, artifact_size_bytes=size,
        sidecar_metadata_digest=observed.get("sidecar_metadata_digest"),
        configuration_digest=str(observed["configuration_digest"]),
        engine_runtime_family=str(observed["engine"]), candidate_index=observed.get("candidate_index"),
        active_production=observed.get("posture") == "production", fallback=bool(observed.get("fallback")),
        authority_record_id="commissioned-authority-record-" + authority_digest[7:31],
        authority_record_digest=authority_digest, active_model_identity=observed,
        active_model_identity_digest=_digest(observed))
    identity.verify()
    return VerifiedCommissionedModel(receipt, proof, path, sha256, size, identity)
