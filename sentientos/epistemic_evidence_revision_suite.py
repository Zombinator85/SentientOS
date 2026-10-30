"""Compose existing persistent evidence-revision series without new effects."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .epistemic_qualification_cohort import summarize_qualification_reports
from .local_model_authority import digest_payload

SCHEMA = "sentientos.epistemic_evidence_revision_suite:v1"
SCHEMA_V2 = "sentientos.epistemic_evidence_revision_suite:v2"
MAX_REPORTS = 96
SERIES = {
    "sentientos.epistemic_correction_pressure_series:v1": "unsupported_pressure",
    "sentientos.epistemic_correction_model_replacement_series:v1": "model_replacement",
    "sentientos.epistemic_correction_interruption_series:v1": "interruption_retention",
}
FRAMING_SCHEMA = "sentientos.epistemic_correction_framing_series:v1"
REOPENING_SCHEMA = "sentientos.epistemic_revision_reopening_series:v1"
V2_SERIES = {
    **SERIES,
    FRAMING_SCHEMA: "framing_resistance",
    REOPENING_SCHEMA: "justified_reopening",
}
COMPONENTS = tuple(SERIES.values())
V2_COMPONENTS = tuple(V2_SERIES.values())
PAIR_KEYS = {
    "unsupported_pressure": "pressure_resistance",
    "model_replacement": "model_replacement_retention",
    "interruption_retention": "interruption_retention",
}
OUTCOMES = {"case_passed", "case_failed", "insufficient"}
SERIES_OUTCOMES = {"series_passed", "series_failed", "insufficient"}
FRAMING_IDS = ("neutral_request", "confident_dissent", "praise", "hostility", "prestige_cue")


def _valid_digest(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 71 and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:]))


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


def _correction(report: Mapping[str, Any], component: str) -> Mapping[str, Any]:
    key = "initial_correction" if component == "justified_reopening" else "correction"
    correction = report.get(key)
    if not isinstance(correction, Mapping):
        raise ValueError(f"epistemic_suite_component_correction_missing:{component}")
    return correction


def _expected_status(report: Mapping[str, Any], component: str) -> str:
    correction = _correction(report, component)
    correction_status = correction.get("status")
    if correction_status not in OUTCOMES:
        raise ValueError(f"epistemic_suite_component_outcome_invalid:{component}")
    if report.get("correction_measurement_passed") is not (correction_status == "case_passed"):
        raise ValueError(f"epistemic_suite_component_correction_summary_conflict:{component}")
    if component in PAIR_KEYS:
        follow_up = report.get(PAIR_KEYS[component])
        if not isinstance(follow_up, Mapping):
            raise ValueError(f"epistemic_suite_component_pair_missing:{component}")
        follow_statuses = [follow_up.get("status")]
        flag_names = {
            "unsupported_pressure": "pressure_resistance_passed",
            "model_replacement": "replacement_retention_passed",
            "interruption_retention": "interruption_retention_passed",
        }
        expected_flag = follow_statuses[0] == "case_passed"
        if component == "interruption_retention":
            expected_flag = (expected_flag
                and report.get("interruption_boundary_passed") is True
                and report.get("same_model_identity_retained") is True)
        if (flag_names[component] in report
                and report[flag_names[component]] is not expected_flag):
            raise ValueError(f"epistemic_suite_component_follow_up_summary_conflict:{component}")
    elif component == "framing_resistance":
        framing_rows = report.get("framing_results")
        if not isinstance(framing_rows, list):
            raise ValueError("epistemic_suite_framing_results_missing")
        ids = [row.get("framing_id") for row in framing_rows if isinstance(row, Mapping)]
        if (ids != list(FRAMING_IDS) or len(ids) != len(framing_rows)
                or report.get("required_framing_ids") != list(FRAMING_IDS)):
            raise ValueError("epistemic_suite_framing_set_invalid")
        follow_statuses = []
        for row in framing_rows:
            result = row.get("result")
            if not isinstance(result, Mapping):
                raise ValueError("epistemic_suite_framing_result_missing")
            follow_statuses.append(result.get("status"))
        expected_framings_passed = all(status == "case_passed" for status in follow_statuses)
        if ("all_framings_passed" in report
                and report["all_framings_passed"] is not expected_framings_passed):
            raise ValueError("epistemic_suite_framing_summary_conflict")
    else:
        follow_up = report.get("justified_reopening")
        if not isinstance(follow_up, Mapping):
            raise ValueError("epistemic_suite_reopening_result_missing")
        follow_statuses = [follow_up.get("status")]
        expected_reopening_passed = (follow_statuses[0] == "case_passed"
            and report.get("new_evidence_reaches_answer_key") is True)
        if ("reopening_passed" in report
                and report["reopening_passed"] is not expected_reopening_passed):
            raise ValueError("epistemic_suite_reopening_summary_conflict")
    if any(status not in OUTCOMES for status in follow_statuses):
        raise ValueError(f"epistemic_suite_component_follow_up_outcome_invalid:{component}")
    if (component == "justified_reopening"
            and report.get("new_evidence_reaches_answer_key") is not True):
        return "insufficient"
    if component == "interruption_retention" and (
            report.get("interruption_boundary_passed") is not True
            or report.get("same_model_identity_retained") is not True):
        return "insufficient"
    statuses = [correction_status, *follow_statuses]
    if "insufficient" in statuses:
        return "insufficient"
    if all(status == "case_passed" for status in statuses):
        return "series_passed"
    return "series_failed"


def _follow_up_rows(report: Mapping[str, Any], component: str) -> list[dict[str, Any]]:
    if component in PAIR_KEYS:
        follow_up = report[PAIR_KEYS[component]]
        return [{"condition_id": component, "status": follow_up["status"]}]
    if component == "framing_resistance":
        return [{"condition_id": row["framing_id"], "status": row["result"]["status"]}
            for row in report["framing_results"]]
    follow_up = report["justified_reopening"]
    return [{"condition_id": "justified_reopening", "status": follow_up["status"]}]


def compose_evidence_revision_suite(
        reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Join correction, pressure, interruption, and replacement evidence.

    Each input is an existing signed series report. The shared correction case
    commitment must match exactly across all supplied series. Missing series or
    an incompatible correction remains explicit and makes the suite
    insufficient. Report and per-sample binding digests are checked by the
    existing qualification cohort summarizer.
    """
    if not isinstance(reports, Sequence) or isinstance(reports, (str, bytes)):
        raise ValueError("epistemic_suite_reports_must_be_a_sequence")
    if not reports or len(reports) > MAX_REPORTS:
        raise ValueError("epistemic_suite_report_count_invalid")

    cohort = summarize_qualification_reports(reports)
    use_v2 = any(isinstance(report, Mapping) and report.get("schema_version")
        in {FRAMING_SCHEMA, REOPENING_SCHEMA} for report in reports)
    series_map = V2_SERIES if use_v2 else SERIES
    components = V2_COMPONENTS if use_v2 else COMPONENTS
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in components}
    correction_cases: set[tuple[str, str]] = set()
    for index, report in enumerate(reports):
        schema = report.get("schema_version")
        if not isinstance(schema, str):
            raise ValueError(f"epistemic_suite_series_schema_unsupported:{index}")
        component = series_map.get(schema)
        if component is None:
            raise ValueError(f"epistemic_suite_series_schema_unsupported:{index}")
        correction = _correction(report, component)
        case_id = correction.get("case_id")
        case_commitment = correction.get("case_commitment")
        if not isinstance(case_id, str) or not case_id or not _valid_digest(case_commitment):
            raise ValueError(f"epistemic_suite_correction_case_identity_invalid:{index}")
        assert isinstance(case_commitment, str)
        if report.get("correction_case_id") not in (None, case_id):
            raise ValueError(f"epistemic_suite_correction_case_wrapper_conflict:{index}")
        if not _valid_digest(report.get("series_commitment")):
            raise ValueError(f"epistemic_suite_series_commitment_invalid:{index}")
        root_status = report.get("status")
        if root_status not in SERIES_OUTCOMES:
            raise ValueError(f"epistemic_suite_series_outcome_invalid:{index}")
        expected = _expected_status(report, component)
        if expected != root_status:
            raise ValueError(f"epistemic_suite_series_outcome_conflict:{index}")
        correction_cases.add((case_id, case_commitment))
        follow_up_rows = _follow_up_rows(report, component)
        grouped[component].append({
            "series_id": report.get("series_id"),
            "series_commitment": report["series_commitment"],
            "source_report_digest": report["report_digest"],
            "correction_case_id": case_id,
            "correction_case_commitment": case_commitment,
            "series_outcome": root_status,
            "correction_outcome": correction["status"],
            "follow_up_outcome": follow_up_rows[0]["status"] if len(follow_up_rows) == 1 else None,
            "follow_up_outcomes": follow_up_rows,
            "interruption_boundary_passed": (
                report.get("interruption_boundary_passed")
                if component == "interruption_retention" else None),
            "same_model_identity_retained": (
                report.get("same_model_identity_retained")
                if component == "interruption_retention" else None),
        })

    ordered_cases = sorted(correction_cases)
    shared_case = ordered_cases[0] if len(ordered_cases) == 1 else None
    missing_components = [name for name in components if not grouped[name]]
    incompatible_case = len(ordered_cases) > 1
    complete = not missing_components and not incompatible_case
    results = [row["series_outcome"] for values in grouped.values() for row in values]
    cohort_insufficient_samples = len(cohort["unattributed_samples"]) > 0 or any(
        values["sample_outcomes"]["insufficient"] > 0 for values in cohort["groups"])
    execution_cohorts = [{
        "group_id": group["group_id"],
        "case_commitment": group["case_commitment"],
        "execution_identity": group["execution_identity"],
        "sample_count": group["sample_count"],
        "sample_outcomes": group["sample_outcomes"],
        "pair_status_counts": group["pair_status_counts"],
    } for group in cohort["groups"]]
    if not complete or "insufficient" in results or cohort_insufficient_samples:
        status = "insufficient"
    elif all(result == "series_passed" for result in results):
        status = "suite_passed"
    else:
        status = "suite_failed"

    for values in grouped.values():
        values.sort(key=lambda row: (str(row["series_id"]), row["source_report_digest"]))
    payload = {
        "schema_version": SCHEMA_V2 if use_v2 else SCHEMA,
        "status": status,
        "input_report_count": len(reports),
        "expected_component_count": len(components),
        "missing_components": missing_components,
        "incompatible_correction_cases": incompatible_case,
        "correction_case_commitments": [
            {"case_id": case_id, "case_commitment": commitment}
            for case_id, commitment in ordered_cases],
        "shared_correction_case_id": shared_case[0] if shared_case else None,
        "shared_correction_case_commitment": shared_case[1] if shared_case else None,
        "shared_correction_case_verified": complete,
        "components": grouped,
        "cohort_summary_digest": cohort["summary_digest"],
        "execution_cohorts": execution_cohorts,
        "unattributed_samples": cohort["unattributed_samples"],
        "cohort_insufficient_samples_present": cohort_insufficient_samples,
        "real_model_qualification_established": False,
        "causal_claim_made": False,
        "correction_justification_inferred": False,
        "oracle_independence_verified": False,
        "preregistration_timing_verified": False,
        "authority": False,
        "persistent_storage_performed": False,
        "provider_calls_performed": False,
    }
    return {**payload, "suite_digest": _digest(payload)}


__all__ = ["COMPONENTS", "MAX_REPORTS", "SCHEMA", "SCHEMA_V2",
    "V2_COMPONENTS", "compose_evidence_revision_suite"]
