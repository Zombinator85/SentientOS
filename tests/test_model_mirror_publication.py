from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.model_mirror_publication import (
    EFFECTS, MODEL_MIRROR_PUBLISH, PRINCIPAL, DeterministicFakeProvider,
    ModelMirrorPublicationError, PublicationGrant, PublicationRequest,
    catalog_deployment_eligibility, file_digest, publication_status, publish,
)

pytestmark = pytest.mark.no_legacy_skip


def fixture(tmp_path: Path):
    root = tmp_path / "escrow"
    root.mkdir(parents=True)
    data = b"GGUF" + b"deterministic-model-bytes" * 8
    artifact = root / "candidate.gguf"
    artifact.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    name = f"candidate-{sha}.gguf"
    url = f"https://models.sentientos.org/{name}"
    package = tmp_path / "curator.json"
    package.write_text(json.dumps({
        "artifact": {"size_bytes": len(data), "sha256": sha, "production_filename": name},
        "candidate_selection": {"selected_model_id": "candidate"},
        "sovereign_mirror": {"destination_url": url},
    }), encoding="utf-8")
    request = PublicationRequest(str(package), file_digest(package), "candidate", str(artifact),
        len(data), sha, name, url, PRINCIPAL, MODEL_MIRROR_PUBLISH, "grant-1", "lease-1", "corr-1")
    grant = PublicationGrant("grant-1", "lease-1", PRINCIPAL, MODEL_MIRROR_PUBLISH,
                             EFFECTS, "corr-1", True)
    ticks = iter(("2026-09-06T00:00:00Z", "2026-09-06T00:01:00Z"))
    return request, grant, DeterministicFakeProvider(), root, tmp_path / "receipt.json", lambda: next(ticks), data


def run(values):
    request, grant, provider, root, receipt, now, _ = values
    return publish(request, grant, provider, artifact_root=root, receipt_path=receipt, now=now)


def test_create_only_streamed_publish_receipt_and_catalog_gate(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    receipt = run(values)
    assert receipt["final_publication_status"] == "published_verified"
    assert receipt["upload_attempted"] is receipt["upload_completed"] is True
    assert receipt["object_exists"] is receipt["object_verified"] is True
    assert receipt["remote_verification_method"] == "complete_streamed_sha256"
    assert receipt["bytes_sent"] == len(values[-1])
    assert catalog_deployment_eligibility(receipt, model_id="candidate",
        artifact_sha256=values[0].artifact_sha256, canonical_url=values[0].canonical_url) == {
            "catalog_deployment_eligible": True, "status": "eligible", "catalog_deployed": False,
            "deployment_authority_granted": False, "receipt_id": receipt["receipt_id"]}


def test_existing_exact_object_is_verified_without_upload(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    values[2].objects[values[0].object_name] = values[-1]
    receipt = run(values)
    assert receipt["final_publication_status"] == "already_present_verified"
    assert receipt["upload_attempted"] is receipt["upload_completed"] is False


@pytest.mark.parametrize("principal", ["stochastic_model", "curator", "maintenance_worker"])
def test_ineligible_principals_cannot_publish(tmp_path: Path, principal: str) -> None:
    values = list(fixture(tmp_path))
    values[1] = replace(values[1], principal=principal)
    with pytest.raises(ModelMirrorPublicationError, match="publication_authority_denied"):
        run(values)
    assert not values[2].objects


@pytest.mark.parametrize("mutation", [
    lambda g: replace(g, active=False),
    lambda g: replace(g, grant_id="wrong"),
    lambda g: replace(g, lease_id="wrong"),
    lambda g: replace(g, effects=frozenset()),
])
def test_definition_artifact_and_configuration_are_not_grants(tmp_path: Path, mutation) -> None:
    values = list(fixture(tmp_path))
    values[1] = mutation(values[1])
    with pytest.raises(ModelMirrorPublicationError, match="publication_authority_denied"):
        run(values)


def test_provider_configuration_is_separate_from_grant(tmp_path: Path) -> None:
    values = list(fixture(tmp_path))
    values[2].configured = False
    with pytest.raises(ModelMirrorPublicationError, match="provider_configuration_unavailable"):
        run(values)


@pytest.mark.parametrize(("field", "value"), [
    ("canonical_url", "https://huggingface.co/candidate.gguf"),
    ("canonical_url", "https://evil.invalid/candidate.gguf"),
    ("object_name", "latest.gguf"),
    ("object_name", "alternate.gguf"),
    ("artifact_sha256", "0" * 64),
])
def test_caller_or_model_cannot_change_destination_or_identity(tmp_path: Path, field: str, value: object) -> None:
    values = list(fixture(tmp_path))
    values[0] = replace(values[0], **{field: value})
    with pytest.raises(ModelMirrorPublicationError):
        run(values)
    assert not values[2].objects


def test_missing_source_and_path_escape_fail_before_provider(tmp_path: Path) -> None:
    values = list(fixture(tmp_path))
    values[0] = replace(values[0], artifact_path=str(tmp_path / "missing.gguf"))
    with pytest.raises(ModelMirrorPublicationError, match="source_missing_or_path_escape"):
        run(values)
    outside = tmp_path / "outside.gguf"
    outside.write_bytes(values[-1])
    values = list(fixture(tmp_path / "second"))
    values[0] = replace(values[0], artifact_path=str(outside))
    with pytest.raises(ModelMirrorPublicationError, match="source_missing_or_path_escape"):
        run(values)


def test_symlink_wrong_size_hash_magic_and_lfs_pointer_are_rejected(tmp_path: Path) -> None:
    for kind in ("symlink", "size", "hash", "magic", "lfs"):
        case = tmp_path / kind
        values = list(fixture(case))
        source = Path(values[0].artifact_path)
        if kind == "symlink":
            target = case / "real.gguf"; source.rename(target); source.symlink_to(target)
        elif kind == "size": source.write_bytes(source.read_bytes() + b"x")
        elif kind == "hash": source.write_bytes(b"GGUF" + b"x" * (values[0].artifact_size - 4))
        elif kind == "magic": source.write_bytes(b"NOPE" + source.read_bytes()[4:])
        else:
            pointer = b"version https://git-lfs.github.com/spec/v1\n"
            source.write_bytes(pointer); values[0] = replace(values[0], artifact_size=len(pointer))
        with pytest.raises(ModelMirrorPublicationError):
            run(values)
        assert not values[2].objects


def test_existing_conflict_is_never_overwritten(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    values[2].objects[values[0].object_name] = b"conflict"
    with pytest.raises(ModelMirrorPublicationError, match="remote_size_mismatch"):
        run(values)
    assert values[2].objects[values[0].object_name] == b"conflict"


@pytest.mark.parametrize(("setup", "code"), [
    (lambda p, d: setattr(p, "interrupt_after_bytes", 1), "transfer_interrupted_or_create_conflict"),
    (lambda p, d: setattr(p, "authentication_failure", True), "provider_authentication_failure"),
    (lambda p, d: setattr(p, "remote_override", d[:-1]), "remote_size_mismatch"),
    (lambda p, d: setattr(p, "remote_override", b"GGUF" + b"x" * (len(d) - 4)), "remote_digest_mismatch"),
])
def test_transfer_and_independent_verification_fail_closed(tmp_path: Path, setup, code: str) -> None:
    values = fixture(tmp_path)
    setup(values[2], values[-1])
    with pytest.raises(ModelMirrorPublicationError, match=code):
        run(values)
    assert not values[4].exists()


def test_receipt_write_failure_does_not_claim_receipt(tmp_path: Path) -> None:
    values = list(fixture(tmp_path))
    blocker = tmp_path / "not-a-directory"; blocker.write_text("x")
    values[4] = blocker / "receipt.json"
    with pytest.raises(ModelMirrorPublicationError, match="receipt_write_failure"):
        run(values)


def test_unverified_receipt_cannot_make_catalog_eligible() -> None:
    gate = catalog_deployment_eligibility({}, model_id="candidate", artifact_sha256="a", canonical_url="https://models.sentientos.org/a")
    assert gate["status"] == "verified_publication_receipt_required"
    assert gate["catalog_deployment_eligible"] is False


def test_contract_has_no_credentials_or_provider_selection_surface(tmp_path: Path) -> None:
    request, *_ = fixture(tmp_path)
    assert not ({"credential", "secret", "token", "provider"} & set(request.__dataclass_fields__))


def test_status_projection_is_structured_and_non_secret(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    receipt = run(values)
    status = publication_status(values[0], values[1], values[2], receipt=receipt)
    assert status["remote_verification_state"] == "verified"
    assert status["catalog_eligibility_state"] == "eligible"
    assert not ({"credential", "secret", "token"} & set(status))
