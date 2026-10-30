"""Verify a signed assessor statement alongside persistent revision evidence.

The signature protects the exact statement and its declared key identity. It
does not establish that the assessor is independent, that the assessment time
is trusted, or that the correction is true or justified.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .causal_resource_principal_ed25519 import (
    CryptographyEd25519SignatureVerifier,
    Ed25519VerificationBackendUnavailable,
)
from .epistemic_pressure_control_suite import (
    LINKED_CONTROL_SCHEMA,
    SCHEMA as PRESSURE_SUITE_SCHEMA,
    compose_pressure_control_revision_suite,
)
from .epistemic_qualification_cohort import MAX_REPORT_BYTES
from .epistemic_revision_qualification import IndependentAnswerKey, RevisionCase
from .local_model_authority import digest_payload

SCHEMA = "sentientos.epistemic_revision_assessment_suite:v1"
ENVELOPE_SCHEMA = "sentientos.epistemic_revision_assessor_attestation:v1"
ATTESTATION_SCHEMA = "sentientos.epistemic_revision_assessor_statement:v1"
ASSESSMENT_OUTCOMES = {"justified", "not_justified", "insufficient"}
STATEMENT_FIELDS = {
    "schema_version", "assessment_id", "case_id", "case_commitment",
    "proposition_digest", "answer_key_digest", "evidence_projection_digests",
    "protocol_digest", "assessor_key_fingerprint", "assessor_role",
    "assessment_outcome", "declared_assessed_at_utc",
}
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def _canonical(value: Any) -> bytes:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False)
    if len(text.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("epistemic_assessment_payload_limit_exceeded")
    return text.encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _verified_object(value: Mapping[str, Any], field: str, error: str) -> dict[str, Any]:
    unsigned = {key: item for key, item in value.items() if key != field}
    supplied = value.get(field)
    if not _valid_digest(supplied) or _digest(unsigned) != supplied:
        raise ValueError(error)
    return unsigned


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return (parsed.tzinfo == timezone.utc
        and parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value)


def revision_case_from_dict(value: Mapping[str, Any]) -> RevisionCase:
    """Rebuild the exact evaluator case from its canonical JSON fields."""
    case_fields = {"case_id", "kind", "proposition_id", "evaluator_version",
        "before_prompt_digest", "after_prompt_digest", "before_key", "after_key",
        "commitment_nonce"}
    key_fields = {"stance", "conclusion", "reason_code", "evidence_ids"}
    if not isinstance(value, Mapping) or set(value) != case_fields:
        raise ValueError("epistemic_assessment_revision_case_invalid")
    try:
        before = value["before_key"]
        after = value["after_key"]
        if (not isinstance(before, Mapping) or set(before) != key_fields
                or not isinstance(after, Mapping) or set(after) != key_fields
                or not isinstance(before["evidence_ids"], (list, tuple))
                or not isinstance(after["evidence_ids"], (list, tuple))):
            raise ValueError("epistemic_assessment_answer_key_invalid")
        case = RevisionCase(
            case_id=value["case_id"], kind=value["kind"],
            proposition_id=value["proposition_id"],
            evaluator_version=value["evaluator_version"],
            before_prompt_digest=value["before_prompt_digest"],
            after_prompt_digest=value["after_prompt_digest"],
            before_key=IndependentAnswerKey(
                stance=before["stance"], conclusion=before["conclusion"],
                reason_code=before["reason_code"], evidence_ids=tuple(before["evidence_ids"])),
            after_key=IndependentAnswerKey(
                stance=after["stance"], conclusion=after["conclusion"],
                reason_code=after["reason_code"], evidence_ids=tuple(after["evidence_ids"])),
            commitment_nonce=value["commitment_nonce"],
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("epistemic_assessment_revision_case_invalid") from exc
    case.commitment()
    return case


def _correction(report: Mapping[str, Any]) -> Mapping[str, Any]:
    value = report.get("initial_correction", report.get("correction"))
    if not isinstance(value, Mapping):
        raise ValueError("epistemic_assessment_source_correction_missing")
    return value


def _case_projection_digests(reports: Sequence[Mapping[str, Any]],
        case: RevisionCase) -> list[str]:
    found: set[str] = set()
    for index, report in enumerate(reports):
        correction = _correction(report)
        if (correction.get("case_id") != case.case_id
                or correction.get("case_commitment") != case.commitment()):
            raise ValueError(f"epistemic_assessment_source_case_mismatch:{index}")
        for condition in ("before", "after"):
            sample = correction.get(condition)
            binding = sample.get("execution_binding") if isinstance(sample, Mapping) else None
            digest = binding.get("projection_digest") if isinstance(binding, Mapping) else None
            if not _valid_digest(digest):
                raise ValueError(f"epistemic_assessment_projection_digest_missing:{index}:{condition}")
            assert isinstance(digest, str)
            found.add(digest)
    if not found:
        raise ValueError("epistemic_assessment_projection_digests_missing")
    return sorted(found)


def _decode_public_key(value: Any) -> bytes:
    if not isinstance(value, str) or _B64URL.fullmatch(value) is None:
        raise ValueError("epistemic_assessment_public_key_invalid")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as exc:
        raise ValueError("epistemic_assessment_public_key_invalid") from exc
    if (len(decoded) != 32
            or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value):
        raise ValueError("epistemic_assessment_public_key_invalid")
    return decoded


def assessor_key_fingerprint(public_key: str) -> str:
    """Return the pin syntax expected by the verifier for a raw Ed25519 key."""
    return "sha256:" + hashlib.sha256(_decode_public_key(public_key)).hexdigest()


def canonical_assessment_statement_bytes(statement: Mapping[str, Any]) -> bytes:
    """Canonical bytes an external assessor signs for an assessment statement."""
    return _canonical(statement)


def _validate_statement(statement: Any, *, case: RevisionCase,
        revision_reports: Sequence[Mapping[str, Any]], expected_protocol_digest: str,
        expected_assessor_key_fingerprint: str) -> dict[str, Any]:
    if not isinstance(statement, Mapping) or set(statement) != STATEMENT_FIELDS:
        raise ValueError("epistemic_assessment_statement_shape_invalid")
    if statement.get("schema_version") != ATTESTATION_SCHEMA:
        raise ValueError("epistemic_assessment_statement_schema_unsupported")
    if (not isinstance(statement.get("assessment_id"), str)
            or not statement["assessment_id"].strip() or len(statement["assessment_id"]) > 128
            or statement.get("assessor_role") != "independent_assessor"
            or statement.get("assessment_outcome") not in ASSESSMENT_OUTCOMES):
        raise ValueError("epistemic_assessment_statement_identity_invalid")
    if (statement.get("case_id") != case.case_id
            or statement.get("case_commitment") != case.commitment()):
        raise ValueError("epistemic_assessment_case_mismatch")
    expected_proposition_digest = _digest({"proposition_id": case.proposition_id})
    expected_answer_key_digest = _digest({
        "before_key": asdict(case.before_key), "after_key": asdict(case.after_key)})
    if (statement.get("proposition_digest") != expected_proposition_digest
            or statement.get("answer_key_digest") != expected_answer_key_digest):
        raise ValueError("epistemic_assessment_case_content_mismatch")
    if statement.get("protocol_digest") != expected_protocol_digest or not _valid_digest(
            expected_protocol_digest):
        raise ValueError("epistemic_assessment_protocol_pin_mismatch")
    if (statement.get("assessor_key_fingerprint") != expected_assessor_key_fingerprint
            or not _valid_digest(expected_assessor_key_fingerprint)):
        raise ValueError("epistemic_assessment_key_pin_mismatch")
    if not _timestamp(statement.get("declared_assessed_at_utc")):
        raise ValueError("epistemic_assessment_declared_time_invalid")
    expected_evidence_digests = _case_projection_digests(revision_reports, case)
    supplied_evidence_digests = statement.get("evidence_projection_digests")
    if (not isinstance(supplied_evidence_digests, list)
            or any(not _valid_digest(item) for item in supplied_evidence_digests)
            or supplied_evidence_digests != sorted(set(supplied_evidence_digests))
            or supplied_evidence_digests != expected_evidence_digests):
        raise ValueError("epistemic_assessment_evidence_binding_mismatch")
    _canonical(statement)
    return dict(statement)


def compose_assessment_attested_revision_suite(*, revision_suite_v2_report: Mapping[str, Any],
        revision_reports: Sequence[Mapping[str, Any]],
        pressure_control_report: Mapping[str, Any], revision_suite_v3_report: Mapping[str, Any],
        correction_case: RevisionCase, attestation: Mapping[str, Any] | None,
        pinned_assessor_public_key: str | None,
        expected_protocol_digest: str | None,
        expected_assessor_key_fingerprint: str | None) -> dict[str, Any]:
    """Compose v3 evidence and a case-bound signed assessor statement.

    The result keeps evidence-suite outcome and assessor-attested outcome
    separate. A valid signature proves only that the supplied public key signed
    the canonical statement. Trust in the key pin, reviewer independence,
    claimed time, and the assessor's judgment remain external.
    """
    if (not isinstance(revision_suite_v2_report, Mapping)
            or not isinstance(revision_suite_v3_report, Mapping)
            or not isinstance(pressure_control_report, Mapping)
            or not isinstance(correction_case, RevisionCase)):
        raise ValueError("epistemic_assessment_source_objects_invalid")
    if (not isinstance(revision_reports, Sequence)
            or isinstance(revision_reports, (str, bytes)) or not revision_reports
            or any(not isinstance(row, Mapping) for row in revision_reports)):
        raise ValueError("epistemic_assessment_revision_reports_invalid")
    if correction_case.kind not in {"contrary_evidence", "inference_correction", "outdated_evidence"}:
        raise ValueError("epistemic_assessment_correction_kind_invalid")
    v3 = compose_pressure_control_revision_suite(
        revision_suite_report=revision_suite_v2_report,
        revision_reports=revision_reports,
        pressure_control_report=pressure_control_report)
    supplied_v3 = _verified_object(
        revision_suite_v3_report, "suite_digest", "epistemic_assessment_v3_digest_mismatch")
    expected_v3 = {key: item for key, item in v3.items() if key != "suite_digest"}
    if supplied_v3 != expected_v3 or v3.get("schema_version") != PRESSURE_SUITE_SCHEMA:
        raise ValueError("epistemic_assessment_v3_source_reports_mismatch")
    if (v3.get("shared_correction_case_id") != correction_case.case_id
            or v3.get("shared_correction_case_commitment") != correction_case.commitment()):
        raise ValueError("epistemic_assessment_suite_case_mismatch")
    linked = pressure_control_report
    if (linked.get("schema_version") != LINKED_CONTROL_SCHEMA
            or linked.get("linked_proposition_digest")
                != _digest({"proposition_id": correction_case.proposition_id})):
        raise ValueError("epistemic_assessment_linked_proposition_mismatch")

    base_status = v3.get("status")
    assessment_status = "missing"
    assessment_outcome: str | None = None
    signature_valid = False
    key_pin_matches = False
    verified_statement: dict[str, Any] | None = None
    reasons: list[str] = []
    if attestation is None:
        reasons.append("assessment_attestation_missing")
    else:
        if (not isinstance(attestation, Mapping)
                or set(attestation) not in (
                    {"schema_version", "statement", "signature"},
                    {"schema_version", "statement"},
                )
                or attestation.get("schema_version") != ENVELOPE_SCHEMA
                or not isinstance(attestation.get("statement"), Mapping)):
            raise ValueError("epistemic_assessment_attestation_shape_invalid")
        if (pinned_assessor_public_key is None or expected_protocol_digest is None
                or expected_assessor_key_fingerprint is None):
            raise ValueError("epistemic_assessment_external_pins_required")
        statement = _validate_statement(
            attestation["statement"], case=correction_case,
            revision_reports=revision_reports,
            expected_protocol_digest=expected_protocol_digest,
            expected_assessor_key_fingerprint=expected_assessor_key_fingerprint)
        public_bytes = _decode_public_key(pinned_assessor_public_key)
        actual_fingerprint = "sha256:" + hashlib.sha256(public_bytes).hexdigest()
        key_pin_matches = (actual_fingerprint == expected_assessor_key_fingerprint
            == statement["assessor_key_fingerprint"])
        if not key_pin_matches:
            raise ValueError("epistemic_assessment_public_key_pin_mismatch")
        signature = attestation.get("signature")
        backend_unavailable = False
        if not isinstance(signature, str):
            signature_valid = False
        else:
            try:
                signature_valid = CryptographyEd25519SignatureVerifier().verify(
                    algorithm="ed25519", public_key=pinned_assessor_public_key,
                    payload=_canonical(statement), signature=signature)
            except Ed25519VerificationBackendUnavailable:
                backend_unavailable = True
                reasons.append("signature_backend_unavailable")
        if backend_unavailable:
            assessment_status = "unavailable"
        elif not signature_valid:
            reasons.append("assessment_signature_invalid")
            assessment_status = "invalid"
        else:
            assessment_status = "signature_verified"
            assessment_outcome = str(statement["assessment_outcome"])
            verified_statement = statement

    if base_status == "insufficient" or assessment_status != "signature_verified":
        experiment_status = "insufficient"
    elif base_status == "suite_failed":
        experiment_status = "suite_failed"
    elif assessment_outcome == "not_justified":
        experiment_status = "assessor_attested_not_justified"
    elif assessment_outcome == "insufficient":
        experiment_status = "insufficient"
    else:
        experiment_status = "suite_passed_with_assessor_attestation"

    payload = {
        "schema_version": SCHEMA,
        "status": experiment_status,
        "evidence_suite_status": base_status,
        "evidence_suite_digest": v3["suite_digest"],
        "shared_correction_case_id": correction_case.case_id,
        "shared_correction_case_commitment": correction_case.commitment(),
        "assessment": {
            "status": assessment_status,
            "attested_outcome": assessment_outcome,
            "signature_valid": signature_valid,
            "public_key_pin_matches": key_pin_matches,
            "attestor_role_declaration": (verified_statement.get("assessor_role")
                if verified_statement is not None else None),
            "statement_digest": (_digest(verified_statement)
                if verified_statement is not None else None),
            "declared_assessed_at_utc": (verified_statement.get("declared_assessed_at_utc")
                if verified_statement is not None else None),
            "claimed_time_verified": False,
            "assessor_independence_verified": False,
            "reasons": reasons,
        },
        "trusted_timestamp_verified": False,
        "correction_truth_verified": False,
        "correction_justification_inferred": False,
        "real_model_qualification_established": False,
        "causal_claim_made": False,
        "provider_calls_performed": False,
        "persistent_storage_performed": False,
        "authority": False,
    }
    return {**payload, "report_digest": _digest(payload)}


__all__ = [
    "ASSESSMENT_OUTCOMES", "ATTESTATION_SCHEMA", "ENVELOPE_SCHEMA", "SCHEMA",
    "assessor_key_fingerprint", "canonical_assessment_statement_bytes",
    "compose_assessment_attested_revision_suite", "revision_case_from_dict",
]
