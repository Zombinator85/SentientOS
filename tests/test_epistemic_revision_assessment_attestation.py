from __future__ import annotations

import base64
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).parent))
from test_epistemic_pressure_control_suite import (  # noqa: E402
    _correction_case,
    _suite_reports,
)
from sentientos.epistemic_evidence_revision_suite import compose_evidence_revision_suite  # noqa: E402
from sentientos.epistemic_pressure_control_suite import (  # noqa: E402
    compose_pressure_control_revision_suite,
)
from sentientos.epistemic_revision_assessment_attestation import (  # noqa: E402
    ATTESTATION_SCHEMA,
    ENVELOPE_SCHEMA,
    assessor_key_fingerprint,
    canonical_assessment_statement_bytes,
    compose_assessment_attested_revision_suite,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402

pytestmark = pytest.mark.no_legacy_skip

PROTOCOL_DIGEST = "sha256:" + "d" * 64


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def _prepared(*, outcome: str = "justified") -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], Any, dict[str, Any], str, str]:
    reports = _suite_reports()
    revision_reports, pressure_control = reports[:-1], reports[-1]
    correction = _correction_case()
    revision_v2 = compose_evidence_revision_suite(revision_reports)
    revision_v3 = compose_pressure_control_revision_suite(
        revision_suite_report=revision_v2,
        revision_reports=revision_reports,
        pressure_control_report=pressure_control,
    )
    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key = base64.urlsafe_b64encode(public_raw).decode("ascii").rstrip("=")
    fingerprint = assessor_key_fingerprint(public_key)
    evidence_digests = sorted({
        sample["execution_binding"]["projection_digest"]
        for report in revision_reports
        for condition in ("before", "after")
        for sample in [report.get("correction", report.get("initial_correction"))[condition]]
    })
    statement = {
        "schema_version": ATTESTATION_SCHEMA,
        "assessment_id": "assessment-001",
        "case_id": correction.case_id,
        "case_commitment": correction.commitment(),
        "proposition_digest": _digest({"proposition_id": correction.proposition_id}),
        "answer_key_digest": _digest({
            "before_key": asdict(correction.before_key),
            "after_key": asdict(correction.after_key),
        }),
        "evidence_projection_digests": evidence_digests,
        "protocol_digest": PROTOCOL_DIGEST,
        "assessor_key_fingerprint": fingerprint,
        "assessor_role": "independent_assessor",
        "assessment_outcome": outcome,
        "declared_assessed_at_utc": "2026-10-29T18:30:00Z",
    }
    signature = private_key.sign(canonical_assessment_statement_bytes(statement))
    attestation = {
        "schema_version": ENVELOPE_SCHEMA,
        "statement": statement,
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }
    return (revision_v2, revision_v3, revision_reports, pressure_control,
        correction, attestation, public_key, fingerprint)


def _compose(prepared: tuple[Any, ...], *, attestation: dict[str, Any] | None = None,
        public_key: str | None = None, fingerprint: str | None = None) -> dict[str, Any]:
    revision_v2, revision_v3, reports, control, correction, signed, key, pin = prepared
    return compose_assessment_attested_revision_suite(
        revision_suite_v2_report=revision_v2,
        revision_suite_v3_report=revision_v3,
        revision_reports=reports,
        pressure_control_report=control,
        correction_case=correction,
        attestation=signed if attestation is None else attestation,
        pinned_assessor_public_key=key if public_key is None else public_key,
        expected_protocol_digest=PROTOCOL_DIGEST,
        expected_assessor_key_fingerprint=pin if fingerprint is None else fingerprint,
    )


def test_valid_signature_binds_assessment_to_exact_persistent_revision_case() -> None:
    prepared = _prepared()
    result = _compose(prepared)
    assert result["status"] == "suite_passed_with_assessor_attestation"
    assert result["assessment"]["status"] == "signature_verified"
    assert result["assessment"]["signature_valid"] is True
    assert result["assessment"]["public_key_pin_matches"] is True
    assert result["assessment"]["attested_outcome"] == "justified"
    assert result["assessment"]["assessor_independence_verified"] is False
    assert result["assessment"]["claimed_time_verified"] is False
    assert result["correction_justification_inferred"] is False
    assert result["provider_calls_performed"] is False


def test_missing_and_negative_assessments_remain_explicit() -> None:
    prepared = _prepared()
    revision_v2, revision_v3, reports, control, correction, *_ = prepared
    missing = compose_assessment_attested_revision_suite(
        revision_suite_v2_report=revision_v2,
        revision_suite_v3_report=revision_v3,
        revision_reports=reports,
        pressure_control_report=control,
        correction_case=correction,
        attestation=None,
        pinned_assessor_public_key=None,
        expected_protocol_digest=None,
        expected_assessor_key_fingerprint=None,
    )
    assert missing["status"] == "insufficient"
    assert missing["assessment"]["status"] == "missing"
    assert missing["evidence_suite_status"] == "suite_passed"

    negative = _compose(_prepared(outcome="not_justified"))
    assert negative["status"] == "assessor_attested_not_justified"
    assert negative["assessment"]["attested_outcome"] == "not_justified"


def test_tampered_signature_fails_closed_without_rewriting_suite_outcome() -> None:
    prepared = _prepared()
    attestation = dict(prepared[5])
    attestation["statement"] = {**attestation["statement"], "assessment_outcome": "not_justified"}
    result = _compose(prepared, attestation=attestation)
    assert result["status"] == "insufficient"
    assert result["evidence_suite_status"] == "suite_passed"
    assert result["assessment"]["status"] == "invalid"
    assert result["assessment"]["signature_valid"] is False

    missing_signature = dict(prepared[5])
    missing_signature.pop("signature")
    result = _compose(prepared, attestation=missing_signature)
    assert result["status"] == "insufficient"
    assert result["assessment"]["signature_valid"] is False


@pytest.mark.parametrize("field", ["case_commitment", "answer_key_digest", "protocol_digest",
    "evidence_projection_digests", "assessor_key_fingerprint"])
def test_mismatched_signed_statement_bindings_are_rejected(field: str) -> None:
    prepared = _prepared()
    attestation = dict(prepared[5])
    statement = dict(attestation["statement"])
    if field == "evidence_projection_digests":
        statement[field] = ["sha256:" + "f" * 64]
    elif field == "protocol_digest":
        statement[field] = "sha256:" + "e" * 64
    else:
        statement[field] = "sha256:" + "f" * 64
    attestation["statement"] = statement
    with pytest.raises(ValueError):
        _compose(prepared, attestation=attestation)


def test_pinned_key_and_v3_source_suite_must_match_exactly() -> None:
    prepared = _prepared()
    with pytest.raises(ValueError, match="key_pin_mismatch"):
        _compose(prepared, fingerprint="sha256:" + "f" * 64)

    revision_v2, revision_v3, reports, control, correction, signed, key, fingerprint = prepared
    tampered = dict(revision_v3)
    tampered["status"] = "suite_failed"
    tampered["suite_digest"] = _digest({k: v for k, v in tampered.items() if k != "suite_digest"})
    with pytest.raises(ValueError, match="v3_source_reports_mismatch"):
        compose_assessment_attested_revision_suite(
            revision_suite_v2_report=revision_v2,
            revision_suite_v3_report=tampered,
            revision_reports=reports,
            pressure_control_report=control,
            correction_case=correction,
            attestation=signed,
            pinned_assessor_public_key=key,
            expected_protocol_digest=PROTOCOL_DIGEST,
            expected_assessor_key_fingerprint=fingerprint,
        )
