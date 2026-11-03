"""Verify operator-issued authority receipts for the split-host companion.

This module verifies authority; it never issues receipts, keys, generations,
or grants. The issuer public keys must be pinned by the target installation
authority and supplied by its platform provider.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
)

RECEIPT_SCHEMA = "sentientos.companion_authority_receipt:v1"
RECEIPT_FIELDS = frozenset({"schema_version", "receipt_type", "issuer_id", "decision",
    "issued_at", "expires_at", "subject", "semantic_digest", "signature"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_RECEIPT_BYTES = 64 * 1024


class CompanionAuthorityReceiptError(CompanionBridgeError):
    """Invalid, expired, untrusted, or mismatched operator authority receipt."""


def canonical_receipt_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise CompanionAuthorityReceiptError("companion_authority_receipt_not_canonical") from exc


def read_companion_authority_receipt(path: Path | str) -> dict[str, Any]:
    """Read a bounded receipt without following its final path component."""
    target = Path(path)
    try:
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise CompanionAuthorityReceiptError("companion_authority_receipt_unavailable") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size <= 0
                or info.st_size > MAX_RECEIPT_BYTES
                or (os.name == "posix" and
                    (info.st_uid != os.getuid() or info.st_mode & 0o022))):
            raise CompanionAuthorityReceiptError("companion_authority_receipt_custody_invalid")
        data = bytearray()
        while len(data) <= MAX_RECEIPT_BYTES:
            block = os.read(fd, min(4096, MAX_RECEIPT_BYTES + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > MAX_RECEIPT_BYTES:
            raise CompanionAuthorityReceiptError("companion_authority_receipt_too_large")
    finally:
        os.close(fd)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CompanionAuthorityReceiptError("companion_authority_receipt_invalid_json") from exc
    if not isinstance(value, dict):
        raise CompanionAuthorityReceiptError("companion_authority_receipt_shape_invalid")
    return value


def generation_receipt_subject(record: BridgeGenerationCustodyRecord) -> dict[str, Any]:
    """Return the exact non-circular generation fields a receipt must authorize."""
    if type(record) is not BridgeGenerationCustodyRecord:
        raise CompanionAuthorityReceiptError("bridge_generation_record_required")
    return {
        "source_id": record.source_id,
        "generation_id": record.generation_id,
        "key_reference": record.key_reference,
        "issuer_id": record.issuer_id,
        "issued_at": record.issued_at,
        "predecessor_generation_id": record.predecessor_generation_id,
    }


def pair_launch_subject(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Bind a pair launch approval to deployment, identity, handoff, and code."""
    required = ("deployment_id", "installation_identity_ref", "runtime_handoff_ref",
                "software_generation_digest")
    if any(not isinstance(manifest.get(field), str) or not manifest[field].strip()
           for field in required):
        raise CompanionAuthorityReceiptError("companion_pair_authority_reference_missing")
    return {
        "action": "launch_pair",
        "deployment_id": manifest["deployment_id"],
        "installation_identity_ref": manifest["installation_identity_ref"],
        "runtime_handoff_ref": manifest["runtime_handoff_ref"],
        "software_generation_digest": manifest["software_generation_digest"],
    }


def role_launch_subject(role: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
    if role not in {"windows_edge", "wsl_core"}:
        raise CompanionAuthorityReceiptError("companion_role_invalid")
    deployment = pair_launch_subject(manifest)
    return {**deployment, "action": "launch_role", "role": role}


def process_launch_subject(*, role: str, command_digest: str,
                            generation: BridgeGenerationPair) -> dict[str, str]:
    if role not in {"windows_edge", "wsl_core"}:
        raise CompanionAuthorityReceiptError("companion_process_role_invalid")
    if (not re.fullmatch(r"[0-9a-f]{64}", command_digest)
            or type(generation) is not BridgeGenerationPair):
        raise CompanionAuthorityReceiptError("companion_process_launch_subject_invalid")
    generation_digest = "sha256:" + hashlib.sha256(
        canonical_receipt_bytes(generation.to_dict())).hexdigest()
    return {"action": "launch_process", "role": role,
            "command_digest": command_digest, "generation_pair_digest": generation_digest}


class SignedCompanionAuthorityVerifier:
    """Verify Ed25519 receipts against issuer keys pinned by platform custody.

    A cryptographically valid receipt is accepted only for the requested type,
    subject, and digest. This verifier does not decide who may become a trusted
    issuer; that remains an installation-level trust-anchor operation.
    """

    def __init__(self, trusted_issuer_public_keys: Mapping[str, bytes], *,
                 clock: Callable[[], datetime] | None = None,
                 maximum_lifetime: timedelta = timedelta(hours=24),
                 future_clock_skew: timedelta = timedelta(seconds=30)) -> None:
        if (not isinstance(trusted_issuer_public_keys, Mapping) or not trusted_issuer_public_keys
                or any(not isinstance(issuer, str) or not _IDENTIFIER.fullmatch(issuer)
                       or not isinstance(key, bytes) or len(key) != 32
                       for issuer, key in trusted_issuer_public_keys.items())):
            raise CompanionAuthorityReceiptError("companion_authority_trust_anchors_invalid")
        if (not isinstance(maximum_lifetime, timedelta)
                or not isinstance(future_clock_skew, timedelta)
                or maximum_lifetime <= timedelta(0) or maximum_lifetime > timedelta(days=7)
                or future_clock_skew < timedelta(0) or future_clock_skew > timedelta(minutes=5)):
            raise CompanionAuthorityReceiptError("companion_authority_time_policy_invalid")
        self._keys = dict(trusted_issuer_public_keys)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._maximum_lifetime = maximum_lifetime
        self._future_clock_skew = future_clock_skew

    def verify(self, receipt: Mapping[str, Any], *, receipt_type: str,
               expected_subject: Mapping[str, Any], expected_digest: str | None = None) -> bool:
        if (not isinstance(receipt, Mapping) or set(receipt) != RECEIPT_FIELDS
                or receipt.get("schema_version") != RECEIPT_SCHEMA
                or receipt.get("receipt_type") != receipt_type
                or not isinstance(receipt_type, str) or not _IDENTIFIER.fullmatch(receipt_type)
                or not isinstance(receipt.get("subject"), Mapping)
                or dict(receipt["subject"]) != dict(expected_subject)):
            raise CompanionAuthorityReceiptError("companion_authority_receipt_subject_mismatch")
        issuer = receipt.get("issuer_id")
        if not isinstance(issuer, str) or issuer not in self._keys:
            raise CompanionAuthorityReceiptError("companion_authority_issuer_untrusted")
        if receipt.get("decision") != "allow":
            raise CompanionAuthorityReceiptError("companion_authority_receipt_not_allow")
        body = {field: receipt[field] for field in (
            "schema_version", "receipt_type", "issuer_id", "decision", "issued_at", "expires_at", "subject")}
        semantic_digest = "sha256:" + hashlib.sha256(canonical_receipt_bytes(body)).hexdigest()
        if (receipt.get("semantic_digest") != semantic_digest
                or not _DIGEST.fullmatch(semantic_digest)
                or (expected_digest is not None and expected_digest != semantic_digest)):
            raise CompanionAuthorityReceiptError("companion_authority_receipt_digest_mismatch")
        issued_at = self._timestamp(receipt.get("issued_at"))
        expires_at = self._timestamp(receipt.get("expires_at"))
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise CompanionAuthorityReceiptError("companion_authority_clock_invalid")
        now = now.astimezone(timezone.utc)
        if (issued_at > now + self._future_clock_skew or expires_at <= now
                or expires_at <= issued_at
                or expires_at - issued_at > self._maximum_lifetime):
            raise CompanionAuthorityReceiptError("companion_authority_receipt_time_invalid")
        signature_text = receipt.get("signature")
        if not isinstance(signature_text, str) or len(signature_text) > 256:
            raise CompanionAuthorityReceiptError("companion_authority_signature_invalid")
        try:
            import base64
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            signature = base64.b64decode(signature_text, validate=True)
            if len(signature) != 64:
                raise ValueError("signature_length")
            Ed25519PublicKey.from_public_bytes(self._keys[issuer]).verify(
                signature, canonical_receipt_bytes(body))
        except ImportError as exc:
            raise CompanionAuthorityReceiptError("companion_authority_crypto_unavailable") from exc
        except (ValueError, InvalidSignature) as exc:
            raise CompanionAuthorityReceiptError("companion_authority_signature_invalid") from exc
        return True

    def verify_generation(self, receipt: Mapping[str, Any], digest: str,
                          record: BridgeGenerationCustodyRecord) -> bool:
        if receipt.get("issuer_id") != record.issuer_id:
            raise CompanionAuthorityReceiptError("bridge_generation_authority_issuer_mismatch")
        if digest != record.authority_receipt_digest:
            raise CompanionAuthorityReceiptError("bridge_generation_authority_digest_binding_mismatch")
        return self.verify(receipt, receipt_type="bridge_generation",
            expected_subject=generation_receipt_subject(record), expected_digest=digest)

    def authorize_pair_launch(self, receipt: Mapping[str, Any], expected_digest: str,
                              manifest: Mapping[str, Any]) -> bool:
        return self.verify(receipt, receipt_type="deployment_launch",
            expected_subject=pair_launch_subject(manifest), expected_digest=expected_digest)

    def authorize_role_launch(self, receipt: Mapping[str, Any], expected_digest: str, *,
                              role: str, manifest: Mapping[str, Any]) -> bool:
        return self.verify(receipt, receipt_type="role_launch",
            expected_subject=role_launch_subject(role, manifest), expected_digest=expected_digest)

    def authorize_process_launch(self, receipt: Mapping[str, Any], expected_digest: str, *,
                                 role: str, command_digest: str,
                                 generation: BridgeGenerationPair) -> bool:
        return self.verify(receipt, receipt_type="process_launch",
            expected_subject=process_launch_subject(role=role, command_digest=command_digest,
                generation=generation), expected_digest=expected_digest)

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if not isinstance(value, str):
            raise CompanionAuthorityReceiptError("companion_authority_timestamp_invalid")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CompanionAuthorityReceiptError("companion_authority_timestamp_invalid") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise CompanionAuthorityReceiptError("companion_authority_timestamp_invalid")
        return parsed.astimezone(timezone.utc)


class CompanionAuthorityReceiptStore:
    """Read operator-issued signed receipts from a provisioned store.

    The store contains ``receipt-<digest>.json`` files for generation receipts
    and ``subject-<digest>.json`` files for launch receipts. It has no writer.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        if self._root.is_symlink() or not self._root.is_dir():
            raise CompanionAuthorityReceiptError("companion_authority_store_unavailable")
        try:
            self._root = self._root.resolve(strict=True)
        except OSError as exc:
            raise CompanionAuthorityReceiptError("companion_authority_store_unavailable") from exc

    def load_digest(self, digest: str) -> dict[str, Any]:
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise CompanionAuthorityReceiptError("companion_authority_receipt_digest_invalid")
        return self._load(self._root / ("receipt-" + digest[7:] + ".json"))

    def load_subject(self, receipt_type: str, subject: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(receipt_type, str) or _IDENTIFIER.fullmatch(receipt_type) is None:
            raise CompanionAuthorityReceiptError("companion_authority_receipt_type_invalid")
        subject_key = {"receipt_type": receipt_type, "subject": dict(subject)}
        key = hashlib.sha256(canonical_receipt_bytes(subject_key)).hexdigest()
        return self._load(self._root / ("subject-" + key + ".json"))

    def _load(self, path: Path) -> dict[str, Any]:
        try:
            path.resolve(strict=True).relative_to(self._root)
        except (OSError, ValueError) as exc:
            raise CompanionAuthorityReceiptError("companion_authority_receipt_outside_store") from exc
        return read_companion_authority_receipt(path)


class CompanionAuthorityCallbacks:
    """Concrete launch and generation callbacks over a pinned verifier/store."""

    def __init__(self, *, verifier: SignedCompanionAuthorityVerifier,
                 store: CompanionAuthorityReceiptStore) -> None:
        self._verifier = verifier
        self._store = store

    def verify_generation(self, receipt_digest: str,
                          record: BridgeGenerationCustodyRecord) -> bool:
        return self._verifier.verify_generation(self._store.load_digest(receipt_digest),
            receipt_digest, record)

    def authorize_pair_launch(self, manifest: Mapping[str, Any]) -> bool:
        subject = pair_launch_subject(manifest)
        receipt = self._store.load_subject("deployment_launch", subject)
        digest = receipt.get("semantic_digest")
        if not isinstance(digest, str):
            raise CompanionAuthorityReceiptError("companion_authority_receipt_digest_invalid")
        return self._verifier.authorize_pair_launch(receipt, digest, manifest)

    def authorize_process_launch(self, role: str, command_digest: str,
                                 generation: BridgeGenerationPair) -> bool:
        subject = process_launch_subject(role=role, command_digest=command_digest,
            generation=generation)
        receipt = self._store.load_subject("process_launch", subject)
        digest = receipt.get("semantic_digest")
        if not isinstance(digest, str):
            raise CompanionAuthorityReceiptError("companion_authority_receipt_digest_invalid")
        return self._verifier.authorize_process_launch(receipt, digest,
            role=role, command_digest=command_digest, generation=generation)

    def authorize_role_launch(self, role: str, manifest: Mapping[str, Any]) -> bool:
        subject = role_launch_subject(role, manifest)
        receipt = self._store.load_subject("role_launch", subject)
        digest = receipt.get("semantic_digest")
        if not isinstance(digest, str):
            raise CompanionAuthorityReceiptError("companion_authority_receipt_digest_invalid")
        return self._verifier.authorize_role_launch(receipt, digest,
            role=role, manifest=manifest)


__all__ = ["RECEIPT_SCHEMA", "CompanionAuthorityReceiptError", "SignedCompanionAuthorityVerifier",
    "CompanionAuthorityReceiptStore", "CompanionAuthorityCallbacks",
    "canonical_receipt_bytes", "generation_receipt_subject", "pair_launch_subject", "role_launch_subject",
    "process_launch_subject", "read_companion_authority_receipt"]
