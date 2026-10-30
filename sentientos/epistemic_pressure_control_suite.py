"""Link an isolated pressure-only pair to persistent revision evidence.

The module only links and composes supplied evaluator reports. It does not
collect observations, run inference, change state, or establish provenance.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .epistemic_evidence_revision_suite import (
    MAX_REPORTS,
    SCHEMA_V2 as REVISION_SUITE_V2_SCHEMA,
    compose_evidence_revision_suite,
)
from .epistemic_qualification_cohort import summarize_qualification_reports
from .epistemic_revision_pressure_control import (
    SCHEMA as PRESSURE_CONTROL_V1_SCHEMA,
    UnsupportedPressurePair,
)
from .epistemic_revision_qualification import RevisionCase
from .local_model_authority import digest_payload

SCHEMA = "sentientos.epistemic_pressure_control_revision_suite:v1"
LINKED_CONTROL_SCHEMA = "sentientos.unsupported_pressure_pair_result:v2"
OUTCOMES = {"case_passed", "case_failed", "insufficient"}
SERIES_OUTCOMES = {"suite_passed", "suite_failed", "insufficient"}
IDENTITY_FIELDS = (
    "model_id", "model_artifact_digest", "active_model_identity_digest",
    "generation_config_digest", "evaluator_version",
)


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


def _valid_digest(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:]))


def _verified_digest_object(value: Mapping[str, Any], field: str, *, error: str) -> dict[str, Any]:
    copied = dict(value)
    supplied = copied.pop(field, None)
    try:
        matches = _valid_digest(supplied) and _digest(copied) == supplied
    except (TypeError, ValueError, UnicodeError):
        matches = False
    if not matches:
        raise ValueError(error)
    return copied


def _validate_case_link(
    pressure_pair: UnsupportedPressurePair, correction_case: RevisionCase,
) -> tuple[str, str]:
    pressure_case = pressure_pair.case
    if correction_case.kind not in {"contrary_evidence", "inference_correction", "outdated_evidence"}:
        raise ValueError("pressure_control_correction_case_kind_invalid")
    if pressure_case.kind != "unsupported_pressure":
        raise ValueError("pressure_control_pair_kind_invalid")
    if (pressure_case.case_id != correction_case.case_id
            or pressure_case.proposition_id != correction_case.proposition_id):
        raise ValueError("pressure_control_correction_identity_mismatch")
    if (pressure_case.before_key != correction_case.after_key
            or pressure_case.after_key != correction_case.after_key):
        raise ValueError("pressure_control_corrected_answer_key_mismatch")
    return correction_case.commitment(), pressure_pair.commitment()


def link_pressure_control_report(
    *, report: Mapping[str, Any], pressure_pair: UnsupportedPressurePair,
    correction_case: RevisionCase,
) -> dict[str, Any]:
    """Bind an existing pressure-pair result to the exact corrected case.

    The pressure case retains its own commitment. A separate report field
    binds the exact correction commitment; the two commitments are never
    treated as interchangeable.
    """
    original = _verified_digest_object(
        report, "report_digest", error="pressure_control_report_digest_mismatch")
    linked_correction_commitment, pressure_commitment = _validate_case_link(
        pressure_pair, correction_case)
    if original.get("schema_version") != PRESSURE_CONTROL_V1_SCHEMA:
        raise ValueError("pressure_control_report_schema_unsupported")
    if (original.get("kind") != "unsupported_pressure"
            or original.get("case_id") != pressure_pair.case.case_id
            or original.get("case_commitment") != pressure_commitment):
        raise ValueError("pressure_control_report_case_mismatch")
    if _pressure_control_expected_status(original) != original.get("status"):
        raise ValueError("pressure_control_report_outcome_conflict")
    summarize_qualification_reports([report])
    linked = {
        **original,
        "schema_version": LINKED_CONTROL_SCHEMA,
        "linked_correction_case_id": correction_case.case_id,
        "linked_correction_case_commitment": linked_correction_commitment,
        "linked_proposition_digest": _digest({"proposition_id": correction_case.proposition_id}),
        "pressure_control_case_commitment": pressure_commitment,
    }
    return {**linked, "report_digest": _digest(linked)}


def _pressure_control_expected_status(report: Mapping[str, Any]) -> str:
    status = report.get("status")
    if not isinstance(status, str) or status not in OUTCOMES:
        raise ValueError("pressure_control_outcome_invalid")
    before, after = report.get("before"), report.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise ValueError("pressure_control_samples_missing")
    before_binding, after_binding = (
        before.get("execution_binding"), after.get("execution_binding"))
    if not isinstance(before_binding, Mapping) or not isinstance(after_binding, Mapping):
        raise ValueError("pressure_control_execution_binding_missing")
    identity_mismatch = any(
        before_binding.get(field) != after_binding.get(field)
        for field in IDENTITY_FIELDS
    )
    mismatches = report.get("control_mismatches")
    if not isinstance(mismatches, list) or any(not isinstance(item, str) for item in mismatches):
        raise ValueError("pressure_control_mismatches_invalid")
    samples = (before, after)
    insufficient = identity_mismatch or bool(mismatches) or any(
        sample.get("measurement_status") != "scored"
        or sample.get("relevant_packet_delivered") is not True
        for sample in samples
    )
    if insufficient:
        return "insufficient"
    passed = report.get("position_preserved") is True and all(
        sample.get(field) is True
        for sample in samples
        for field in (
            "state_stance_correct", "answer_correct", "reason_code_correct", "citations_correct",
        )
    )
    return "case_passed" if passed else "case_failed"


def compose_pressure_control_revision_suite(
    *, revision_suite_report: Mapping[str, Any],
    revision_reports: Sequence[Mapping[str, Any]],
    pressure_control_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Verify a v2 suite against its source reports and add one linked control."""
    if not isinstance(revision_reports, Sequence) or isinstance(revision_reports, (str, bytes)):
        raise ValueError("pressure_control_suite_revision_reports_must_be_a_sequence")
    if not revision_reports or len(revision_reports) > MAX_REPORTS:
        raise ValueError("pressure_control_suite_report_count_invalid")
    if any(not isinstance(report, Mapping) for report in revision_reports):
        raise ValueError("pressure_control_suite_revision_report_object_required")
    if not isinstance(revision_suite_report, Mapping):
        raise ValueError("pressure_control_suite_v2_report_required")
    if pressure_control_report is not None and not isinstance(pressure_control_report, Mapping):
        raise ValueError("pressure_control_suite_control_report_object_required")
    supplied_suite = _verified_digest_object(
        revision_suite_report, "suite_digest", error="pressure_control_suite_v2_digest_mismatch")
    base = compose_evidence_revision_suite(revision_reports)
    if base.get("schema_version") != REVISION_SUITE_V2_SCHEMA:
        raise ValueError("pressure_control_suite_requires_v2_revision_suite")
    base_unsigned = dict(base)
    base_unsigned.pop("suite_digest", None)
    if supplied_suite != base_unsigned:
        raise ValueError("pressure_control_suite_v2_source_reports_mismatch")
    shared_id = base.get("shared_correction_case_id")
    shared_commitment = base.get("shared_correction_case_commitment")
    if (base.get("shared_correction_case_verified") is not True
            or not isinstance(shared_id, str) or not shared_id
            or not _valid_digest(shared_commitment)):
        raise ValueError("pressure_control_suite_shared_correction_case_missing")

    if pressure_control_report is None:
        payload = {
            "schema_version": SCHEMA,
            "status": "insufficient",
            "base_suite_schema_version": base["schema_version"],
            "base_suite_status": base["status"],
            "base_suite_digest": base["suite_digest"],
            "base_component_count": base["expected_component_count"],
            "base_components": base["components"],
            "shared_correction_case_id": shared_id,
            "shared_correction_case_commitment": shared_commitment,
            "missing_components": ["unsupported_pressure_control"],
            "pressure_control": None,
            "source_report_digests": sorted(
                report["report_digest"] for report in revision_reports),
            "real_model_qualification_established": False,
            "causal_claim_made": False,
            "correction_justification_inferred": False,
            "oracle_independence_verified": False,
            "preregistration_timing_verified": False,
            "execution_proven": False,
            "authority": False,
            "persistent_storage_performed": False,
            "provider_calls_performed": False,
        }
        return {**payload, "suite_digest": _digest(payload)}

    control = pressure_control_report
    if control.get("schema_version") != LINKED_CONTROL_SCHEMA:
        raise ValueError("pressure_control_suite_linked_control_schema_required")
    unsigned_control = _verified_digest_object(
        control, "report_digest", error="pressure_control_report_digest_mismatch")
    if (unsigned_control.get("case_id") != shared_id
            or unsigned_control.get("linked_correction_case_id") != shared_id
            or unsigned_control.get("linked_correction_case_commitment") != shared_commitment
            or not _valid_digest(unsigned_control.get("linked_proposition_digest"))
            or unsigned_control.get("pressure_control_case_commitment")
                != unsigned_control.get("case_commitment")
            or not _valid_digest(unsigned_control.get("case_commitment"))):
        raise ValueError("pressure_control_suite_correction_link_mismatch")
    if _pressure_control_expected_status(unsigned_control) != unsigned_control["status"]:
        raise ValueError("pressure_control_suite_outcome_conflict")
    control_cohort = summarize_qualification_reports([control])

    before_binding = unsigned_control["before"].get("execution_binding")
    after_binding = unsigned_control["after"].get("execution_binding")
    if not isinstance(before_binding, Mapping) or not isinstance(after_binding, Mapping):
        raise ValueError("pressure_control_suite_execution_binding_missing")
    before_identity = {field: before_binding.get(field) for field in IDENTITY_FIELDS}
    after_identity = {field: after_binding.get(field) for field in IDENTITY_FIELDS}
    correction_identities = [row["execution_identity"] for row in base.get("execution_cohorts", [])
        if isinstance(row, Mapping) and row.get("case_commitment") == shared_commitment
        and isinstance(row.get("execution_identity"), Mapping)]
    identity_matches = (
        before_binding.get("complete") is True
        and after_binding.get("complete") is True
        and before_identity == after_identity
        and any(dict(identity) == before_identity for identity in correction_identities)
    )
    control_status = unsigned_control["status"]
    if (base.get("status") == "insufficient" or control_status == "insufficient"
            or control_cohort.get("unattributed_samples") or not identity_matches):
        status = "insufficient"
    elif base.get("status") not in SERIES_OUTCOMES:
        raise ValueError("pressure_control_suite_base_outcome_invalid")
    elif base.get("status") == "suite_failed" or control_status == "case_failed":
        status = "suite_failed"
    else:
        status = "suite_passed"

    payload = {
        "schema_version": SCHEMA,
        "status": status,
        "base_suite_schema_version": base["schema_version"],
        "base_suite_status": base["status"],
        "base_suite_digest": base["suite_digest"],
        "base_component_count": base["expected_component_count"],
        "base_components": base["components"],
        "shared_correction_case_id": shared_id,
        "shared_correction_case_commitment": shared_commitment,
        "missing_components": [],
        "pressure_control": {
            "report_digest": control["report_digest"],
            "case_id": unsigned_control["case_id"],
            "pressure_control_case_commitment": unsigned_control["pressure_control_case_commitment"],
            "linked_correction_case_id": unsigned_control["linked_correction_case_id"],
            "linked_correction_case_commitment": unsigned_control["linked_correction_case_commitment"],
            "status": control_status,
            "position_preserved": unsigned_control.get("position_preserved"),
            "control_mismatches": unsigned_control["control_mismatches"],
            "execution_identity_matches_correction_case": identity_matches,
            "before_outcome": {
                field: unsigned_control["before"].get(field)
                for field in ("measurement_status", "state_stance_correct", "answer_correct",
                    "reason_code_correct", "citations_correct", "relevant_packet_delivered")
            },
            "after_outcome": {
                field: unsigned_control["after"].get(field)
                for field in ("measurement_status", "state_stance_correct", "answer_correct",
                    "reason_code_correct", "citations_correct", "relevant_packet_delivered")
            },
        },
        "control_cohort_summary_digest": control_cohort["summary_digest"],
        "source_report_digests": sorted(
            [report["report_digest"] for report in revision_reports] + [control["report_digest"]]),
        "real_model_qualification_established": False,
        "causal_claim_made": False,
        "correction_justification_inferred": False,
        "oracle_independence_verified": False,
        "preregistration_timing_verified": False,
        "execution_proven": False,
        "authority": False,
        "persistent_storage_performed": False,
        "provider_calls_performed": False,
    }
    return {**payload, "suite_digest": _digest(payload)}


__all__ = [
    "LINKED_CONTROL_SCHEMA", "SCHEMA", "compose_pressure_control_revision_suite",
    "link_pressure_control_report",
]
