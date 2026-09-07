from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model_catalog import local_model_catalog_digest, validate_local_model_catalog
from sentientos.local_model_catalog_deployment import (
    CatalogDeploymentAuthority, CatalogDeploymentRequest, deploy_local_model_catalog,
    verify_deployment_receipt,
)
from sentientos.local_model_catalog_deployment_architecture import EFFECTS, EXPECTED_ABSENT, semantic_digest
from sentientos.model_catalog_custody import ModelCatalogCustody
from sentientos.model_mirror_publication import RECEIPT_SCHEMA

pytestmark = pytest.mark.no_legacy_skip
NOW = "2026-09-07T12:00:00Z"


def catalog(priority: int = 1) -> dict[str, object]:
    digest = "a" * 64
    filename = f"fixture-{digest}.gguf"
    value = {"schema_version": "sentientos.local_model_catalog:v1", "models": [{
        "model_id": "fixture", "priority": priority, "license_id": "apache-2.0",
        "source_repository": "example/fixture", "source_revision": "b" * 40,
        "source_artifact_filename": "models/fixture.gguf", "artifact_filename": filename,
        "artifact_sha256": digest, "artifact_size_bytes": 42, "artifact_content_address": f"sha256:{digest}",
        "artifact_urls": [f"https://models.sentientos.org/{filename}"],
        "requirements": {"architecture": "x86_64", "ram_gb_min": 1, "avx": False, "avx2": False,
                         "avx512": False, "quantization": "q4"},
        "execution_routes": [{"route_id": "cpu", "engine": "llama_cpp", "backend_family": "cpu",
                              "route_priority": 1}],
    }]}
    return validate_local_model_catalog(value)


def publication(candidate: dict[str, object]) -> dict[str, object]:
    model = candidate["models"][0]  # type: ignore[index]
    body = {"schema_version": RECEIPT_SCHEMA, "model_id": "fixture", "artifact_sha256": model["artifact_sha256"],
            "artifact_size": model["artifact_size_bytes"], "canonical_url": model["artifact_urls"][0],
            "object_exists": True, "object_verified": True,
            "remote_verification_method": "complete_streamed_sha256", "remote_digest": model["artifact_sha256"],
            "remote_size": model["artifact_size_bytes"], "final_publication_status": "published_verified",
            "catalog_deployment_eligible": True, "catalog_deployed": False}
    body["receipt_id"] = "model-publication-" + semantic_digest(body)[:24]
    body["receipt_semantic_digest"] = semantic_digest(body)
    return body


def setup(tmp_path: Path, candidate: dict[str, object], expected: str = EXPECTED_ABSENT):
    handle = InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("fixture"), create=True)
    digest = local_model_catalog_digest(candidate)
    custody = ModelCatalogCustody.for_installation(handle)
    request = CatalogDeploymentRequest("deterministic_catalog_deployment_controller",
        "sentientos.local_model_catalog.deploy", EFFECTS, "grant", "lease", "corr", "fixture",
        custody.custody_identity, digest, expected)
    authority = CatalogDeploymentAuthority("grant", "lease", request.principal, request.capability_id, EFFECTS,
        "corr", "fixture", custody.custody_identity, digest, expected, True,
        "2026-09-07T00:00:00Z", "2026-09-08T00:00:00Z", synthetic_test_authority=True)
    return handle, request, authority, custody


def test_valid_genesis_deployment_writes_exact_catalog_receipt_and_finalization(tmp_path: Path) -> None:
    candidate = catalog(); handle, request, authority, custody = setup(tmp_path, candidate)
    result = deploy_local_model_catalog(handle, request, authority, candidate, [publication(candidate)], now=lambda: NOW)
    assert result.status == "deployed_verified"
    assert handle.read_regular(custody.authoritative_catalog).decode() == __import__("json").dumps(
        candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    receipt = __import__("json").loads(handle.read_regular(custody.deployment_receipts.child(f"{result.receipt_id}.json")))
    assert verify_deployment_receipt(receipt)
    assert handle.read_regular(custody.transactions.child(f"{result.transaction_id}.final.json"))


def test_exact_digest_replacement_and_stale_contender(tmp_path: Path) -> None:
    first = catalog(); handle, request, authority, _ = setup(tmp_path, first)
    assert deploy_local_model_catalog(handle, request, authority, first, [publication(first)], now=lambda: NOW).status == "deployed_verified"
    second = catalog(2); prior = local_model_catalog_digest(first)
    _, request2, authority2, _ = setup(tmp_path, second, prior)
    # setup returns another handle authenticated to the same registry-derived root.
    assert deploy_local_model_catalog(handle, request2, authority2, second, [publication(second)], now=lambda: NOW).status == "deployed_verified"
    assert deploy_local_model_catalog(handle, request2, authority2, second, [publication(second)], now=lambda: NOW).status == "stale_prior_state"


@pytest.mark.parametrize("change", [
    lambda a: replace(a, active=False), lambda a: replace(a, expires_at="2026-09-07T00:00:00Z"),
    lambda a: replace(a, principal="curator"), lambda a: replace(a, capability_id="wrong"),
    lambda a: replace(a, effects=EFFECTS[:-1]), lambda a: replace(a, effects=EFFECTS + ("extra",)),
    lambda a: replace(a, effects=EFFECTS + (EFFECTS[0],)), lambda a: replace(a, correlation_id="wrong"),
    lambda a: replace(a, installation_identity="other"), lambda a: replace(a, custody_identity="wrong"),
    lambda a: replace(a, candidate_catalog_semantic_digest="0" * 64), lambda a: replace(a, expected_prior_state="0" * 64),
])
def test_malformed_or_mismatched_authority_is_denied(tmp_path: Path, change) -> None:
    candidate = catalog(); handle, request, authority, _ = setup(tmp_path, candidate)
    assert deploy_local_model_catalog(handle, request, change(authority), candidate, [publication(candidate)], now=lambda: NOW).status == "authority_denied"


@pytest.mark.parametrize("field,value", [("object_verified", False), ("remote_verification_method", "etag"),
                                           ("remote_digest", "0" * 64), ("remote_size", 41),
                                           ("final_publication_status", "uploaded")])
def test_forged_publication_eligibility_never_bypasses_complete_verification(tmp_path: Path, field: str, value: object) -> None:
    candidate = catalog(); handle, request, authority, _ = setup(tmp_path, candidate)
    receipt = publication(candidate); receipt[field] = value
    assert deploy_local_model_catalog(handle, request, authority, candidate, [receipt], now=lambda: NOW).status == "verified_publication_evidence_required"


def test_missing_extra_and_digest_tampered_publication_evidence_fail(tmp_path: Path) -> None:
    candidate = catalog(); handle, request, authority, _ = setup(tmp_path, candidate)
    assert deploy_local_model_catalog(handle, request, authority, candidate, [], now=lambda: NOW).status == "verified_publication_evidence_required"
    bad = publication(candidate); bad["receipt_semantic_digest"] = "0" * 64
    assert deploy_local_model_catalog(handle, request, authority, candidate, [bad], now=lambda: NOW).status == "verified_publication_evidence_required"


def test_candidate_digest_mismatch_and_existing_malformed_state_fail_closed(tmp_path: Path) -> None:
    candidate = catalog(); handle, request, authority, custody = setup(tmp_path, candidate)
    assert deploy_local_model_catalog(handle, replace(request, proposed_catalog_semantic_digest="0" * 64), authority,
                                      candidate, [publication(candidate)], now=lambda: NOW).status == "authority_denied"
    custody.initialize_directories(); handle.durable_create(custody.authoritative_catalog, b"not-json")
    assert deploy_local_model_catalog(handle, request, authority, candidate, [publication(candidate)], now=lambda: NOW).status == "manual_recovery_required"
