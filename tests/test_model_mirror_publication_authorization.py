from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.model_mirror_publication import PublicationProviderConfiguration, semantic_digest
from sentientos.model_mirror_publication_authorization import (
    APPROVAL_SCHEMA, ISSUANCE_CAPABILITY, ISSUANCE_EFFECTS, ISSUER_PRINCIPAL,
    ModelMirrorPublicationAuthorizationApproval, ModelMirrorPublicationAuthorizationError,
    ModelMirrorPublicationAuthorizationRequest, build_publication_intent,
    issue_model_mirror_publication_authorization, project_model_mirror_publication_authority,
    with_semantic_digest,
)

pytestmark = pytest.mark.no_legacy_skip
START = "2026-09-28T12:00:00Z"
END = "2026-09-28T12:45:00Z"
LEASE_END = "2026-09-28T12:30:00Z"


def fixture(tmp_path: Path):
    root = tmp_path / "escrow"; root.mkdir()
    data = b"GGUF" + b"bounded-test-model" * 8
    artifact = root / "model.gguf"; artifact.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest(); name = f"model-{digest}.gguf"
    package = tmp_path / "curator.json"
    package.write_text(json.dumps({"artifact": {"size_bytes": len(data), "sha256": digest, "production_filename": name},
      "candidate_selection": {"selected_model_id": "model"},
      "sovereign_mirror": {"destination_url": f"https://models.sentientos.org/{name}"}}))
    config = PublicationProviderConfiguration.build("deterministic_fake", "fake:test", "memory:test",
      "models.sentientos.org", "credential-store:test-key")
    intent = build_publication_intent(intent_id="intent-1", curator_package_path=str(package),
      curator_package_sha256=hashlib.sha256(package.read_bytes()).hexdigest(), model_id="model",
      artifact_path=str(artifact), artifact_sha256=digest, artifact_size=len(data), object_name=name,
      canonical_url=f"https://models.sentientos.org/{name}", publication_correlation_id="publish-correlation",
      provider_configuration_identity=config.provider_identity, provider_configuration_digest=config.configuration_digest)
    request = ModelMirrorPublicationAuthorizationRequest(ISSUER_PRINCIPAL, ISSUANCE_CAPABILITY, ISSUANCE_EFFECTS,
      "authorization-correlation", "publish-correlation", intent.intent_id, intent.semantic_digest,
      START, END, START, LEASE_END)
    approval = ModelMirrorPublicationAuthorizationApproval("approval-1", "operator-alice", "operator-console:test",
      "approved", ISSUANCE_CAPABILITY, ISSUER_PRINCIPAL, ISSUANCE_EFFECTS, request.authorization_correlation_id,
      request.publication_correlation_id, intent.intent_id, intent.semantic_digest, intent.curator_package_sha256,
      intent.model_id, intent.artifact_sha256, intent.artifact_size, intent.object_name, intent.canonical_url,
      intent.target_publication_capability, intent.target_publication_principal, intent.target_effect_set_digest,
      intent.provider_configuration_identity, intent.provider_configuration_digest, START, END, START, LEASE_END,
      True, "", APPROVAL_SCHEMA)
    approval = with_semantic_digest(approval)
    handle = InstallationStateRegistry._for_testing(tmp_path / "state").open(InstallationIdentity("fixture"), create=True)
    kernel = ControlPlaneKernel(decisions_path=tmp_path / "decisions.jsonl")
    return handle, kernel, request, approval, intent, config, root


def issue(values):
    return issue_model_mirror_publication_authorization(values[0], values[2], values[3], values[4], values[1],
      created_at=START, allow_synthetic_test_evidence=True)


def test_finite_issuance_projection_and_create_only_replay(tmp_path: Path) -> None:
    values = fixture(tmp_path); result = issue(values)
    assert result.status == "issued"
    authority = project_model_mirror_publication_authority(result.grant, result.lease, result.receipt, values[4],
      observed_at=START, allow_synthetic_test_authority=True)
    assert authority.publication_intent_digest == values[4].semantic_digest
    assert result.grant.not_before <= result.lease.not_before < result.lease.expires_at <= result.grant.expires_at
    # Replay uses a fresh kernel because admission dedupe correctly prevents a second effect admission.
    values = list(values); values[1] = ControlPlaneKernel(decisions_path=tmp_path / "replay.jsonl")
    assert issue(values).status == "replayed"


@pytest.mark.parametrize(("mutation", "code"), [
  (lambda r, a, i: (r, None, i), "operator_approval_missing"),
  (lambda r, a, i: (r, with_semantic_digest(replace(a, approval_status="denied", semantic_digest="")), i), "operator_approval_required"),
  (lambda r, a, i: (r, with_semantic_digest(replace(a, operator_identity="placeholder", semantic_digest="")), i), "operator_identity_invalid"),
  (lambda r, a, i: (replace(r, issuer_principal="wrong"), a, i), "issuer_authority_denied"),
  (lambda r, a, i: (replace(r, issuance_effects=()), a, i), "issuance_effects_invalid"),
  (lambda r, a, i: (replace(r, grant_expires_at="2026-09-28T14:00:00Z"), a, i), "grant_interval_invalid"),
  (lambda r, a, i: (replace(r, lease_expires_at="2026-09-28T13:00:00Z"), a, i), "lease_interval_invalid"),
  (lambda r, a, i: (replace(r, publication_correlation_id=r.authorization_correlation_id), a, i), "approval_intent_binding_mismatch"),
])
def test_issuance_fails_closed(tmp_path: Path, mutation, code: str) -> None:
    values = list(fixture(tmp_path)); request, approval, intent = mutation(values[2], values[3], values[4])
    if approval is None:
        with pytest.raises(ModelMirrorPublicationAuthorizationError, match=code):
            issue_model_mirror_publication_authorization(values[0], request, approval, intent, values[1], created_at=START)
        return
    with pytest.raises(ModelMirrorPublicationAuthorizationError, match=code):
        issue_model_mirror_publication_authorization(values[0], request, approval, intent, values[1], created_at=START,
          allow_synthetic_test_evidence=True)


def test_synthetic_production_and_revocation_fail_closed(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    with pytest.raises(ModelMirrorPublicationAuthorizationError, match="synthetic_approval_forbidden"):
        issue_model_mirror_publication_authorization(values[0], values[2], values[3], values[4], values[1], created_at=START)
    result = issue(values)
    revocation = {"schema_version": "sentientos.model_mirror_publication_authorization_revocation:v1",
      "revocation_id": "revoke-1", "grant_id": result.grant.grant_id, "lease_id": None, "active": True,
      "effective_at": START, "reason": "operator"}
    revocation["semantic_digest"] = semantic_digest(revocation)
    with pytest.raises(ModelMirrorPublicationAuthorizationError, match="authorization_revoked"):
        project_model_mirror_publication_authority(result.grant, result.lease, result.receipt, values[4],
          observed_at=START, revocations=(revocation,), allow_synthetic_test_authority=True)


def test_no_raw_secret_in_authority_evidence(tmp_path: Path) -> None:
    secret = "CONSPICUOUS-SYNTHETIC-SECRET-DO-NOT-LEAK"
    values = fixture(tmp_path); result = issue(values)
    serialized = json.dumps([asdict(values[4]), asdict(values[3]), asdict(result.grant), asdict(result.lease),
      asdict(result.receipt), asdict(values[5])], sort_keys=True)
    assert secret not in serialized
