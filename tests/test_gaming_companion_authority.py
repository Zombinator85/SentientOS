from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.gaming_companion_authority import (
    RECEIPT_SCHEMA,
    CompanionAuthorityReceiptError,
    SignedCompanionAuthorityVerifier,
    canonical_receipt_bytes,
    generation_receipt_subject,
    pair_launch_subject,
    process_launch_subject,
    role_launch_subject,
    read_companion_authority_receipt,
    CompanionAuthorityCallbacks,
    CompanionAuthorityReceiptStore,
)
from sentientos.gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
)

pytestmark = pytest.mark.no_legacy_skip

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def _signer():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    return private, public


def _receipt(private, *, receipt_type: str, subject: dict[str, object],
             issued_at: datetime = NOW - timedelta(seconds=1),
             expires_at: datetime = NOW + timedelta(minutes=5)) -> dict[str, object]:
    body = {
        "schema_version": RECEIPT_SCHEMA,
        "receipt_type": receipt_type,
        "issuer_id": "fixture-operator-authority",
        "decision": "allow",
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "subject": subject,
    }
    digest = "sha256:" + hashlib.sha256(canonical_receipt_bytes(body)).hexdigest()
    signature = base64.b64encode(private.sign(canonical_receipt_bytes(body))).decode("ascii")
    return {**body, "semantic_digest": digest, "signature": signature}


def _record() -> BridgeGenerationCustodyRecord:
    return BridgeGenerationCustodyRecord(
        source_id="windows-edge", generation_id="edge-generation-2",
        key_reference="dpapi:edge-generation-2", issuer_id="fixture-operator-authority",
        issued_at=(NOW - timedelta(seconds=1)).isoformat(),
        authority_receipt_digest="sha256:" + "a" * 64,
        predecessor_generation_id="edge-generation-1")


def test_signed_generation_receipt_verifies_exact_record_and_digest() -> None:
    private, public = _signer()
    record = _record()
    receipt = _receipt(private, receipt_type="bridge_generation",
                       subject=generation_receipt_subject(record))
    verifier = SignedCompanionAuthorityVerifier({"fixture-operator-authority": public},
        clock=lambda: NOW)

    bound_record = BridgeGenerationCustodyRecord(
        record.source_id, record.generation_id, record.key_reference, record.issuer_id,
        record.issued_at, str(receipt["semantic_digest"]), record.predecessor_generation_id)
    assert verifier.verify_generation(receipt, str(receipt["semantic_digest"]), bound_record) is True


def test_generation_receipt_subject_binds_key_and_predecessor() -> None:
    private, public = _signer()
    record = _record()
    receipt = _receipt(private, receipt_type="bridge_generation",
                       subject=generation_receipt_subject(record))
    changed = BridgeGenerationCustodyRecord(
        record.source_id, record.generation_id, "dpapi:other-key", record.issuer_id,
        record.issued_at, str(receipt["semantic_digest"]), record.predecessor_generation_id)
    verifier = SignedCompanionAuthorityVerifier({"fixture-operator-authority": public},
        clock=lambda: NOW)

    with pytest.raises(CompanionAuthorityReceiptError,
                       match="companion_authority_receipt_subject_mismatch"):
        verifier.verify_generation(receipt, str(receipt["semantic_digest"]), changed)


def test_pair_and_process_launch_subjects_bind_runtime_identity_and_exact_command() -> None:
    manifest = {"deployment_id": "glorp-companion", "installation_identity_ref": "install:glorp",
        "runtime_handoff_ref": "runtime-handoff:active", "software_generation_digest": "sha256:" + "b" * 64}
    assert pair_launch_subject(manifest) == {
        "action": "launch_pair", "deployment_id": "glorp-companion",
        "installation_identity_ref": "install:glorp", "runtime_handoff_ref": "runtime-handoff:active",
        "software_generation_digest": "sha256:" + "b" * 64}
    assert role_launch_subject("wsl_core", manifest) == {
        "action": "launch_role", "role": "wsl_core", "deployment_id": "glorp-companion",
        "installation_identity_ref": "install:glorp", "runtime_handoff_ref": "runtime-handoff:active",
        "software_generation_digest": "sha256:" + "b" * 64}
    generation = BridgeGenerationPair(_record(), BridgeGenerationCustodyRecord(
        "wsl-core", "core-generation-2", "posix:core-key", "fixture-operator-authority",
        (NOW - timedelta(seconds=1)).isoformat(), "sha256:" + "d" * 64, "core-generation-1"))
    assert process_launch_subject(role="wsl_core", command_digest="c" * 64,
        generation=generation)["command_digest"] == "c" * 64
    with pytest.raises(CompanionAuthorityReceiptError,
                       match="companion_process_launch_subject_invalid"):
        process_launch_subject(role="wsl_core", command_digest="bad",
            generation=generation)


@pytest.mark.parametrize("mutation,reason", [
    ("signature", "companion_authority_signature_invalid"),
    ("issuer", "companion_authority_issuer_untrusted"),
    ("expiry", "companion_authority_receipt_time_invalid"),
    ("lifetime", "companion_authority_receipt_time_invalid"),
    ("digest", "companion_authority_receipt_digest_mismatch"),
])
def test_authority_verifier_rejects_tamper_untrusted_stale_and_rebound_receipts(
        mutation: str, reason: str) -> None:
    private, public = _signer()
    subject = {"action": "launch_pair", "deployment_id": "fixture"}
    receipt = _receipt(private, receipt_type="deployment_launch", subject=subject)
    expected_digest = str(receipt["semantic_digest"])
    if mutation == "signature":
        receipt["signature"] = base64.b64encode(b"z" * 64).decode("ascii")
    elif mutation == "issuer":
        receipt["issuer_id"] = "unknown-issuer"
        body = {key: receipt[key] for key in (
            "schema_version", "receipt_type", "issuer_id", "issued_at", "expires_at", "subject")}
        receipt["semantic_digest"] = "sha256:" + hashlib.sha256(canonical_receipt_bytes(body)).hexdigest()
        expected_digest = str(receipt["semantic_digest"])
    elif mutation == "expiry":
        receipt = _receipt(private, receipt_type="deployment_launch", subject=subject,
            issued_at=NOW - timedelta(minutes=10), expires_at=NOW - timedelta(minutes=1))
        expected_digest = str(receipt["semantic_digest"])
    elif mutation == "lifetime":
        receipt = _receipt(private, receipt_type="deployment_launch", subject=subject,
            issued_at=NOW - timedelta(days=2), expires_at=NOW + timedelta(days=1))
        expected_digest = str(receipt["semantic_digest"])
    else:
        expected_digest = "sha256:" + "0" * 64
    verifier = SignedCompanionAuthorityVerifier({"fixture-operator-authority": public},
        clock=lambda: NOW)

    with pytest.raises(CompanionAuthorityReceiptError, match=reason):
        verifier.verify(receipt, receipt_type="deployment_launch",
            expected_subject=subject, expected_digest=expected_digest)


def test_signed_receipt_denial_is_not_mistaken_for_launch_authorization() -> None:
    private, public = _signer()
    subject = {"action": "launch_pair", "deployment_id": "fixture"}
    receipt = _receipt(private, receipt_type="deployment_launch", subject=subject)
    receipt["decision"] = "deny"
    body = {key: receipt[key] for key in (
        "schema_version", "receipt_type", "issuer_id", "decision", "issued_at", "expires_at", "subject")}
    receipt["semantic_digest"] = "sha256:" + hashlib.sha256(canonical_receipt_bytes(body)).hexdigest()
    receipt["signature"] = base64.b64encode(private.sign(canonical_receipt_bytes(body))).decode("ascii")
    verifier = SignedCompanionAuthorityVerifier({"fixture-operator-authority": public},
        clock=lambda: NOW)

    with pytest.raises(CompanionAuthorityReceiptError,
                       match="companion_authority_receipt_not_allow"):
        verifier.verify(receipt, receipt_type="deployment_launch", expected_subject=subject)


def test_receipt_file_reader_rejects_symlink_and_accepts_bounded_private_file(tmp_path: Path) -> None:
    private, _public = _signer()
    receipt = _receipt(private, receipt_type="deployment_launch", subject={"deployment_id": "fixture"})
    target = tmp_path / "receipt.json"
    target.write_text(json.dumps(receipt), encoding="utf-8")
    os.chmod(target, 0o600)
    assert read_companion_authority_receipt(target)["semantic_digest"] == receipt["semantic_digest"]
    link = tmp_path / "receipt-link.json"
    link.symlink_to(target)
    with pytest.raises(CompanionAuthorityReceiptError,
                       match="companion_authority_receipt_unavailable"):
        read_companion_authority_receipt(link)


def test_concrete_callbacks_resolve_signed_pair_and_generation_receipts(tmp_path: Path) -> None:
    private, public = _signer()
    root = tmp_path / "authority-store"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    verifier = SignedCompanionAuthorityVerifier({"fixture-operator-authority": public},
        clock=lambda: NOW)
    store = CompanionAuthorityReceiptStore(root)
    callbacks = CompanionAuthorityCallbacks(verifier=verifier, store=store)

    manifest = {"deployment_id": "glorp-companion", "installation_identity_ref": "install:glorp",
        "runtime_handoff_ref": "handoff:active", "software_generation_digest": "sha256:" + "b" * 64}
    pair_subject = pair_launch_subject(manifest)
    pair_receipt = _receipt(private, receipt_type="deployment_launch", subject=pair_subject)
    subject_key = hashlib.sha256(canonical_receipt_bytes(
        {"receipt_type": "deployment_launch", "subject": pair_subject})).hexdigest()
    pair_path = root / ("subject-" + subject_key + ".json")
    pair_path.write_text(json.dumps(pair_receipt), encoding="utf-8")
    os.chmod(pair_path, 0o600)
    assert callbacks.authorize_pair_launch(manifest) is True

    role_subject = role_launch_subject("wsl_core", manifest)
    role_receipt = _receipt(private, receipt_type="role_launch", subject=role_subject)
    role_key = hashlib.sha256(canonical_receipt_bytes(
        {"receipt_type": "role_launch", "subject": role_subject})).hexdigest()
    role_path = root / ("subject-" + role_key + ".json")
    role_path.write_text(json.dumps(role_receipt), encoding="utf-8")
    os.chmod(role_path, 0o600)
    assert callbacks.authorize_role_launch("wsl_core", manifest) is True

    record = _record()
    generation_receipt = _receipt(private, receipt_type="bridge_generation",
        subject=generation_receipt_subject(record))
    generation_digest = str(generation_receipt["semantic_digest"])
    bound_record = BridgeGenerationCustodyRecord(
        record.source_id, record.generation_id, record.key_reference, record.issuer_id,
        record.issued_at, generation_digest, record.predecessor_generation_id)
    generation_path = root / ("receipt-" + generation_digest[7:] + ".json")
    generation_path.write_text(json.dumps(generation_receipt), encoding="utf-8")
    os.chmod(generation_path, 0o600)
    assert callbacks.verify_generation(generation_digest, bound_record) is True

    pair = BridgeGenerationPair(bound_record, BridgeGenerationCustodyRecord(
        "wsl-core", "core-generation-2", "posix:core-key", "fixture-operator-authority",
        (NOW - timedelta(seconds=1)).isoformat(), "sha256:" + "d" * 64, "core-generation-1"))
    process_subject = process_launch_subject(role="wsl_core", command_digest="c" * 64,
        generation=pair)
    process_receipt = _receipt(private, receipt_type="process_launch", subject=process_subject)
    process_key = hashlib.sha256(canonical_receipt_bytes(
        {"receipt_type": "process_launch", "subject": process_subject})).hexdigest()
    process_path = root / ("subject-" + process_key + ".json")
    process_path.write_text(json.dumps(process_receipt), encoding="utf-8")
    os.chmod(process_path, 0o600)
    assert callbacks.authorize_process_launch("wsl_core", "c" * 64, pair) is True


def test_receipt_verifier_rejects_non_json_subject_values() -> None:
    with pytest.raises(CompanionAuthorityReceiptError,
                       match="companion_authority_receipt_not_canonical"):
        canonical_receipt_bytes({"not_json": float("nan")})
