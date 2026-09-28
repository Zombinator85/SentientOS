from __future__ import annotations

from pathlib import Path
from dataclasses import asdict, replace

import pytest

from sentientos.model_mirror_publication import (
    DeterministicFakeProvider, ModelMirrorPublicationError, catalog_deployment_eligibility, publish,
)
from sentientos.model_mirror_publication_authorization import (
    issue_model_mirror_publication_authorization, materialize_publication_request,
    project_model_mirror_publication_authority,
)
from tests.test_model_mirror_publication_authorization import START, fixture

pytestmark = pytest.mark.no_legacy_skip


def test_same_kernel_two_admissions_publish_and_reconstruct_eligibility(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    result = issue_model_mirror_publication_authorization(values[0], values[2], values[3], values[4], values[1],
      created_at=START, allow_synthetic_test_evidence=True)
    authority = project_model_mirror_publication_authority(result.grant, result.lease, result.receipt, values[4],
      observed_at=START, allow_synthetic_test_authority=True)
    request = materialize_publication_request(values[4], authority)
    ticks = iter((START, "2026-09-28T12:01:00Z")); provider = DeterministicFakeProvider()
    receipt = publish(request, authority, provider, artifact_root=values[6], receipt_path=tmp_path / "receipt.json",
      now=lambda: next(ticks), kernel=values[1], provider_configuration=values[5])
    assert values[2].authorization_correlation_id != request.correlation_id
    assert receipt["publication_control_plane_admission_reference"] == "kernel_decision:publish-correlation"
    assert receipt["authorization_issuance_receipt_digest"] == result.receipt.semantic_digest
    assert catalog_deployment_eligibility(receipt, model_id=request.model_id,
      artifact_sha256=request.artifact_sha256, canonical_url=request.canonical_url)["catalog_deployment_eligible"] is True


def test_reusing_issuance_correlation_defers_before_provider_access(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    result = issue_model_mirror_publication_authorization(values[0], values[2], values[3], values[4], values[1],
      created_at=START, allow_synthetic_test_evidence=True)
    authority = project_model_mirror_publication_authority(result.grant, result.lease, result.receipt, values[4],
      observed_at=START, allow_synthetic_test_authority=True)
    request = materialize_publication_request(values[4], authority)
    request = replace(request, correlation_id=values[2].authorization_correlation_id)
    authority = replace(authority, correlation_id=values[2].authorization_correlation_id, authority_semantic_digest="")
    from sentientos.model_mirror_publication import semantic_digest
    body = asdict(authority); body.pop("authority_semantic_digest"); body["effects"] = sorted(authority.effects)
    authority = replace(authority, authority_semantic_digest=semantic_digest(body))
    provider = DeterministicFakeProvider()
    with pytest.raises(ModelMirrorPublicationError, match="publication_effect_admission_denied"):
        publish(request, authority, provider, artifact_root=values[6], receipt_path=tmp_path / "receipt.json",
          now=lambda: START, kernel=values[1], provider_configuration=values[5])
    assert provider.objects == {}
