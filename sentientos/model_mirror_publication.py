"""Deterministic, create-only sovereign model mirror publication boundary.

The provider is injected by the operator.  This module never discovers providers,
credentials, or destinations and never gives a request (or artifact possession)
authority to publish.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, Protocol
from urllib.parse import urlsplit

from sentientos.codex_task_authority_admission import AUTHORITY_DEFINITIONS, MODEL_MIRROR_PUBLISH
from sentientos.control_plane_kernel import (
    AdmissionOutcome, AuthorityClass, ControlActionRequest, ControlPlaneKernel, LifecyclePhase,
)

REQUEST_SCHEMA = "sentientos.model_mirror_publication_request:v1"
GRANT_SCHEMA = "sentientos.model_mirror_publication_grant:v1"
HARDENED_GRANT_SCHEMA = "sentientos.model_mirror_publication_grant:v2"
PROVIDER_CONFIG_SCHEMA = "sentientos.model_mirror_publication_provider_config:v1"
RECEIPT_SCHEMA = "sentientos.model_mirror_publication_receipt:v1"
CANONICAL_HOST = "models.sentientos.org"
PRINCIPAL = "deterministic_publication_controller"
EFFECTS = frozenset(AUTHORITY_DEFINITIONS[MODEL_MIRROR_PUBLISH].required_effects)
CHUNK_SIZE = 1024 * 1024


class ModelMirrorPublicationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def semantic_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PublicationRequest:
    curator_package_path: str
    curator_package_sha256: str
    model_id: str
    artifact_path: str
    artifact_size: int
    artifact_sha256: str
    object_name: str
    canonical_url: str
    authority_principal: str
    capability_id: str
    grant_id: str
    lease_id: str
    correlation_id: str
    schema_version: str = REQUEST_SCHEMA


@dataclass(frozen=True)
class PublicationGrant:
    grant_id: str
    lease_id: str
    principal: str
    capability_id: str
    effects: frozenset[str]
    correlation_id: str
    active: bool
    schema_version: str = GRANT_SCHEMA
    publication_intent_digest: str = ""
    publication_request_binding_digest: str = ""
    authorization_receipt_id: str = ""
    authorization_receipt_digest: str = ""
    provider_configuration_digest: str = ""
    valid_not_before: str = ""
    valid_expires_at: str = ""
    synthetic_test_authority: bool = False
    authority_semantic_digest: str = ""


@dataclass(frozen=True)
class PublicationProviderConfiguration:
    """Operator-owned, non-secret provider metadata; the reference is not a credential."""
    provider_kind: str
    provider_identity: str
    storage_namespace_identity: str
    canonical_public_host: str
    opaque_credential_reference: str
    configuration_digest: str
    schema_version: str = PROVIDER_CONFIG_SCHEMA

    @classmethod
    def build(cls, provider_kind: str, provider_identity: str, storage_namespace_identity: str,
              canonical_public_host: str, opaque_credential_reference: str) -> "PublicationProviderConfiguration":
        body = {"provider_kind": provider_kind, "provider_identity": provider_identity,
                "storage_namespace_identity": storage_namespace_identity,
                "canonical_public_host": canonical_public_host,
                "opaque_credential_reference": opaque_credential_reference,
                "schema_version": PROVIDER_CONFIG_SCHEMA}
        return cls(**{k: str(v) for k, v in body.items() if k != "schema_version"},
                   configuration_digest=semantic_digest(body))


@dataclass(frozen=True)
class RemoteObject:
    exists: bool
    size: int | None = None
    provider_digest: str | None = None


class PublicationProvider(Protocol):
    """Narrow operator-injected adapter; credentials stay inside the adapter."""
    provider_identity: str
    configured: bool

    def inspect(self, object_name: str) -> RemoteObject: ...
    def create_only(self, object_name: str, chunks: Iterable[bytes]) -> str: ...
    def read_chunks(self, object_name: str) -> Iterable[bytes]: ...


@dataclass
class DeterministicFakeProvider:
    """In-memory test provider.  It is explicitly not a production adapter."""
    objects: dict[str, bytes] = field(default_factory=dict)
    configured: bool = True
    provider_identity: str = "deterministic_fake_provider:test_only"
    interrupt_after_bytes: int | None = None
    authentication_failure: bool = False
    remote_override: bytes | None = None

    def inspect(self, object_name: str) -> RemoteObject:
        data = self.objects.get(object_name)
        return RemoteObject(data is not None, len(data) if data is not None else None)

    def create_only(self, object_name: str, chunks: Iterable[bytes]) -> str:
        if self.authentication_failure:
            raise PermissionError("authentication failed")
        if object_name in self.objects:
            raise FileExistsError(object_name)
        data = bytearray()
        for chunk in chunks:
            data.extend(chunk)
            if self.interrupt_after_bytes is not None and len(data) >= self.interrupt_after_bytes:
                raise OSError("interrupted transfer")
        self.objects[object_name] = bytes(data)
        return "fake-upload:" + semantic_digest({"name": object_name, "size": len(data)})[:16]

    def read_chunks(self, object_name: str) -> Iterable[bytes]:
        data = self.remote_override if self.remote_override is not None else self.objects[object_name]
        for offset in range(0, len(data), CHUNK_SIZE):
            yield data[offset:offset + CHUNK_SIZE]


def load_curator_package(path: Path, expected_digest: str) -> Mapping[str, object]:
    if not path.is_file() or path.is_symlink() or file_digest(path) != expected_digest:
        raise ModelMirrorPublicationError("curator_package_identity_mismatch")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelMirrorPublicationError("curator_package_invalid") from exc
    if not isinstance(value, Mapping):
        raise ModelMirrorPublicationError("curator_package_invalid")
    return value


def _validate_request(request: PublicationRequest, package: Mapping[str, object]) -> None:
    artifact = package.get("artifact")
    selection = package.get("candidate_selection")
    mirror = package.get("sovereign_mirror")
    if not isinstance(artifact, Mapping) or not isinstance(selection, Mapping) or not isinstance(mirror, Mapping):
        raise ModelMirrorPublicationError("curator_package_invalid")
    expected = {
        "model_id": selection.get("selected_model_id"),
        "artifact_size": artifact.get("size_bytes"),
        "artifact_sha256": artifact.get("sha256"),
        "object_name": artifact.get("production_filename"),
        "canonical_url": mirror.get("destination_url"),
    }
    if any(getattr(request, key) != value for key, value in expected.items()):
        raise ModelMirrorPublicationError("request_curator_binding_mismatch")
    parsed = urlsplit(request.canonical_url)
    if parsed.scheme != "https" or parsed.hostname != CANONICAL_HOST or parsed.username or parsed.password or parsed.port:
        raise ModelMirrorPublicationError("destination_not_canonical_sovereign")
    if Path(parsed.path).name != request.object_name or parsed.path != "/" + request.object_name:
        raise ModelMirrorPublicationError("destination_object_name_mismatch")
    if request.artifact_sha256 not in request.object_name or "latest" in request.object_name.casefold():
        raise ModelMirrorPublicationError("mutable_or_non_content_addressed_object")
    if request.schema_version != REQUEST_SCHEMA:
        raise ModelMirrorPublicationError("request_schema_invalid")


def _admit_authority(request: PublicationRequest, grant: PublicationGrant) -> None:
    accepted_schema = grant.schema_version in {GRANT_SCHEMA, HARDENED_GRANT_SCHEMA}
    hardened = grant.schema_version == HARDENED_GRANT_SCHEMA
    if (not accepted_schema or not grant.active or grant.principal != PRINCIPAL or
            grant.capability_id != MODEL_MIRROR_PUBLISH or grant.effects != EFFECTS or
            request.authority_principal != grant.principal or request.capability_id != grant.capability_id or
            request.grant_id != grant.grant_id or request.lease_id != grant.lease_id or
            request.correlation_id != grant.correlation_id):
        raise ModelMirrorPublicationError("publication_authority_denied")
    if hardened:
        body = asdict(grant); claimed = body.pop("authority_semantic_digest")
        body["effects"] = sorted(grant.effects)
        if (claimed != semantic_digest(body) or not grant.publication_intent_digest or
                not grant.publication_request_binding_digest or not grant.authorization_receipt_digest):
            raise ModelMirrorPublicationError("publication_authority_denied")


def verify_local_artifact(request: PublicationRequest, artifact_root: Path) -> str:
    source = Path(request.artifact_path)
    if source.is_symlink():
        raise ModelMirrorPublicationError("source_symlink_forbidden")
    try:
        root = artifact_root.resolve(strict=True)
        resolved = source.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ModelMirrorPublicationError("source_missing_or_path_escape") from exc
    if not resolved.is_file() or resolved.stat().st_size != request.artifact_size:
        raise ModelMirrorPublicationError("source_size_mismatch")
    with resolved.open("rb") as stream:
        prefix = stream.read(128)
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ModelMirrorPublicationError("git_lfs_pointer_not_artifact")
    if prefix[:4] != b"GGUF":
        raise ModelMirrorPublicationError("gguf_magic_mismatch")
    digest = file_digest(resolved)
    if digest != request.artifact_sha256:
        raise ModelMirrorPublicationError("source_digest_mismatch")
    return digest


def _remote_digest(provider: PublicationProvider, object_name: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    for chunk in provider.read_chunks(object_name):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def _write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ModelMirrorPublicationError("receipt_already_exists")
        handle, temporary = tempfile.mkstemp(prefix=".publication-", dir=path.parent)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except ModelMirrorPublicationError:
        raise
    except OSError as exc:
        raise ModelMirrorPublicationError("receipt_write_failure") from exc
    finally:
        if "temporary" in locals():
            Path(temporary).unlink(missing_ok=True)


def publish(request: PublicationRequest, grant: PublicationGrant, provider: PublicationProvider | None,
            *, artifact_root: Path, receipt_path: Path, now: Callable[[], str],
            kernel: ControlPlaneKernel | None = None,
            provider_configuration: PublicationProviderConfiguration | None = None) -> dict[str, object]:
    """Verify, create (never overwrite), independently verify, and write a receipt."""
    _admit_authority(request, grant)
    admission_ref = "legacy_test_compatibility:no_effect_admission"
    if grant.schema_version == HARDENED_GRANT_SCHEMA:
        if kernel is None or provider_configuration is None:
            raise ModelMirrorPublicationError("publication_effect_admission_required")
        config_body = asdict(provider_configuration); config_digest = config_body.pop("configuration_digest")
        if (provider_configuration.schema_version != PROVIDER_CONFIG_SCHEMA or
                config_digest != semantic_digest(config_body) or config_digest != grant.provider_configuration_digest or
                provider_configuration.canonical_public_host != CANONICAL_HOST):
            raise ModelMirrorPublicationError("provider_configuration_invalid")
        metadata = {"correlation_id": request.correlation_id,
                    "publication_intent_digest": grant.publication_intent_digest,
                    "publication_authority_digest": grant.authority_semantic_digest,
                    "curator_package_digest": request.curator_package_sha256,
                    "model_id": request.model_id, "artifact_sha256": request.artifact_sha256,
                    "artifact_size": request.artifact_size, "object_name": request.object_name,
                    "canonical_url": request.canonical_url,
                    "provider_identity": provider_configuration.provider_identity,
                    "provider_configuration_digest": config_digest,
                    "target_effect_set_digest": semantic_digest(sorted(EFFECTS))}
        decision = kernel.admit(ControlActionRequest("publish_model_mirror_object",
            AuthorityClass.MODEL_MIRROR_PUBLICATION, PRINCIPAL, "model_distribution",
            LifecyclePhase.RUNTIME, metadata=metadata))
        if (decision.outcome != AdmissionOutcome.ALLOW or decision.actor != PRINCIPAL or
                decision.authority_class != AuthorityClass.MODEL_MIRROR_PUBLICATION or
                decision.correlation_id != request.correlation_id):
            raise ModelMirrorPublicationError("publication_effect_admission_denied")
        admission_ref = decision.admission_decision_ref
    package_path = Path(request.curator_package_path)
    package = load_curator_package(package_path, request.curator_package_sha256)
    _validate_request(request, package)
    local_digest = verify_local_artifact(request, artifact_root)
    if provider is None or not provider.configured:
        raise ModelMirrorPublicationError("provider_configuration_unavailable")
    started = now()
    transferred = 0
    upload_attempted = False
    upload_completed = False
    upload_identity: str | None = None
    existing = provider.inspect(request.object_name)

    def chunks() -> Iterator[bytes]:
        nonlocal transferred
        with Path(request.artifact_path).open("rb") as source:
            for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                transferred += len(chunk)
                yield chunk

    if not existing.exists:
        upload_attempted = True
        try:
            upload_identity = provider.create_only(request.object_name, chunks())
            upload_completed = True
        except PermissionError as exc:
            raise ModelMirrorPublicationError("provider_authentication_failure") from exc
        except (OSError, FileExistsError) as exc:
            raise ModelMirrorPublicationError("transfer_interrupted_or_create_conflict") from exc
    remote_size, remote_digest = _remote_digest(provider, request.object_name)
    if remote_size != request.artifact_size:
        raise ModelMirrorPublicationError("remote_size_mismatch")
    if remote_digest != request.artifact_sha256:
        raise ModelMirrorPublicationError("remote_digest_mismatch_custody_violation")
    verified_at = now()
    status = "published_verified" if upload_completed else "already_present_verified"
    body: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA, "model_id": request.model_id,
        "curator_package_sha256": request.curator_package_sha256,
        "artifact_sha256": request.artifact_sha256, "artifact_size": request.artifact_size,
        "object_name": request.object_name, "canonical_url": request.canonical_url,
        "publication_principal": grant.principal, "capability_id": grant.capability_id,
        "grant_id": grant.grant_id, "lease_id": grant.lease_id, "correlation_id": grant.correlation_id,
        "authorization_grant_id": grant.grant_id, "authorization_lease_id": grant.lease_id,
        "authorization_issuance_receipt_id": grant.authorization_receipt_id,
        "authorization_issuance_receipt_digest": grant.authorization_receipt_digest,
        "publication_intent_digest": grant.publication_intent_digest,
        "publication_authority_digest": grant.authority_semantic_digest,
        "publication_request_binding_digest": grant.publication_request_binding_digest,
        "publication_control_plane_admission_reference": admission_ref,
        "provider_configuration_identity": provider_configuration.provider_identity if provider_configuration else None,
        "provider_configuration_digest": grant.provider_configuration_digest,
        "target_effect_set_digest": semantic_digest(sorted(EFFECTS)),
        "provider_identity": provider.provider_identity, "provider_upload_identity": upload_identity,
        "transfer_started_at": started, "transfer_ended_at": verified_at,
        "bytes_read": transferred, "bytes_sent": transferred,
        "upload_attempted": upload_attempted, "upload_completed": upload_completed,
        "object_exists": True, "object_verified": True,
        "create_state": "newly_created" if upload_completed else "already_present",
        "upload_outcome": "completed" if upload_completed else "not_needed",
        "remote_verification_method": "complete_streamed_sha256",
        "remote_size": remote_size, "remote_digest": remote_digest,
        "verified_local_digest": local_digest, "verification_timestamp": verified_at,
        "final_publication_status": status, "catalog_deployment_eligible": True,
        "catalog_deployed": False,
    }
    body["receipt_id"] = "model-publication-" + semantic_digest(body)[:24]
    body["receipt_semantic_digest"] = semantic_digest(body)
    _write_receipt(receipt_path, body)
    return body


def catalog_deployment_eligibility(receipt: Mapping[str, object], *, model_id: str,
                                   artifact_sha256: str, canonical_url: str) -> dict[str, object]:
    copy = dict(receipt)
    claimed = copy.pop("receipt_semantic_digest", None)
    eligible = (
        receipt.get("schema_version") == RECEIPT_SCHEMA and claimed == semantic_digest(copy) and
        receipt.get("model_id") == model_id and receipt.get("artifact_sha256") == artifact_sha256 and
        receipt.get("canonical_url") == canonical_url and receipt.get("object_verified") is True and
        receipt.get("remote_verification_method") == "complete_streamed_sha256" and
        receipt.get("final_publication_status") in {"published_verified", "already_present_verified"}
    )
    return {"catalog_deployment_eligible": eligible,
            "status": "eligible" if eligible else "verified_publication_receipt_required",
            "catalog_deployed": False, "deployment_authority_granted": False,
            "receipt_id": receipt.get("receipt_id") if eligible else None}


def publication_status(request: PublicationRequest, grant: PublicationGrant,
                       provider: PublicationProvider | None, *, receipt: Mapping[str, object] | None = None,
                       failure: ModelMirrorPublicationError | None = None) -> dict[str, object]:
    """Return a bounded, non-secret operational projection."""
    evidence = receipt or {}
    return {
        "requested_model_artifact": request.artifact_path,
        "verified_local_digest": evidence.get("verified_local_digest"),
        "publication_principal": grant.principal,
        "capability_id": grant.capability_id,
        "grant_id": grant.grant_id,
        "lease_id": grant.lease_id,
        "provider_class": provider.provider_identity if provider is not None else "unconfigured",
        "canonical_destination": request.canonical_url,
        "transfer_state": evidence.get("upload_outcome", "not_started" if failure is None else "failed"),
        "bytes_transferred": evidence.get("bytes_sent", 0),
        "create_state": evidence.get("create_state", "not_created"),
        "remote_verification_state": "verified" if evidence.get("object_verified") else "unverified",
        "receipt_identity": evidence.get("receipt_id"),
        "catalog_eligibility_state": "eligible" if evidence.get("catalog_deployment_eligible") else "ineligible",
        "failure_reason": failure.code if failure is not None else None,
    }
