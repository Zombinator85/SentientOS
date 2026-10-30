from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.compose_epistemic_evidence_revision_suite import main as compose_main
from sentientos.epistemic_evidence_revision_suite import compose_evidence_revision_suite
from sentientos.epistemic_revision_framing_series import FRAMING_IDS
from sentientos.epistemic_qualification_execution_binding import build_execution_binding
from sentientos.local_model_authority import digest_payload

pytestmark = pytest.mark.no_legacy_skip

PRESSURE = "sentientos.epistemic_correction_pressure_series:v1"
REPLACEMENT = "sentientos.epistemic_correction_model_replacement_series:v1"
INTERRUPTION = "sentientos.epistemic_correction_interruption_series:v1"
CORRECTION_COMMITMENT = "sha256:" + "a" * 64


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def _signed(value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "report_digest": _digest(value)}


def _sample(condition: str, case_id: str, *, model: str = "model-a",
        passed: bool = True, citations: bool = True) -> dict[str, Any]:
    binding = build_execution_binding(
        case_id=case_id, evaluator_version="suite-test-v1", condition=condition,
        model_id=model, model_artifact_digest="sha256:" + "1" * 64,
        active_model_identity={"model": model, "content": model + "-content"},
        generation_config={"temperature": 0}, prompt_digest="sha256:" + "2" * 64,
        projection_digest="sha256:" + "3" * 64,
        observation_digest="sha256:" + "4" * 64,
        receipt_digest="sha256:" + "5" * 64,
        output_digest="sha256:" + "6" * 64)
    return {
        "execution_binding": binding,
        "execution_status": "admitted_completed",
        "measurement_status": "scored",
        "state_stance_correct": passed,
        "answer_correct": passed,
        "reason_code_correct": passed,
        "citations_correct": citations,
    }


def _pair(case_id: str, commitment: str, *, status: str = "case_passed",
        before_model: str = "model-a", after_model: str = "model-a",
        after_passed: bool = True, citations: bool = True) -> dict[str, Any]:
    return _signed({
        "schema_version": "sentientos.epistemic_revision_case_result:v1",
        "case_id": case_id,
        "case_commitment": commitment,
        "evaluator_version": "suite-test-v1",
        "status": status,
        "before": _sample("before", case_id, model=before_model),
        "after": _sample("after", case_id, model=after_model,
            passed=after_passed, citations=citations),
    })


def _reports(*, correction_commitment: str = CORRECTION_COMMITMENT,
        pressure_status: str = "case_passed", include: tuple[str, ...] = (
            PRESSURE, REPLACEMENT, INTERRUPTION)) -> list[dict[str, Any]]:
    correction = _pair("persistent-correction", correction_commitment)
    reports: list[dict[str, Any]] = []
    for schema in include:
        if schema == PRESSURE:
            follow = _pair("pressure-only", "sha256:" + "b" * 64,
                status=pressure_status, after_passed=pressure_status == "case_passed")
            component = "unsupported_pressure"
            follow_key = "pressure_resistance"
            extra: dict[str, Any] = {}
        elif schema == REPLACEMENT:
            follow = _pair("replacement-retention", "sha256:" + "c" * 64,
                before_model="model-a", after_model="model-b")
            component = "model_replacement"
            follow_key = "model_replacement_retention"
            extra = {}
        else:
            follow = _pair("interruption-retention", "sha256:" + "d" * 64)
            component = "interruption_retention"
            follow_key = "interruption_retention"
            extra = {"interruption_boundary_passed": True,
                "same_model_identity_retained": True}
        reports.append(_signed({
            "schema_version": schema,
            "series_id": "suite:" + component,
            "series_commitment": "sha256:" + "e" * 64,
            "status": "series_failed" if pressure_status == "case_failed" and schema == PRESSURE
                else "series_passed",
            "correction": correction,
            follow_key: follow,
            "correction_measurement_passed": correction["status"] == "case_passed",
            **extra,
        }))
    return reports


def _extended_reports(*, framing_status: str = "case_passed",
        reopening_status: str = "case_passed",
        new_evidence_reaches_answer_key: bool = True) -> list[dict[str, Any]]:
    reports = _reports()
    correction = _pair("persistent-correction", CORRECTION_COMMITMENT)
    framing_results = [{"framing_id": framing_id, "result": _pair(
        "framing:" + framing_id, "sha256:" + str(index + 3) * 64,
        status=framing_status, after_passed=framing_status == "case_passed")}
        for index, framing_id in enumerate(FRAMING_IDS)]
    frame_root_status = "series_passed" if framing_status == "case_passed" else "series_failed"
    reports.append(_signed({
        "schema_version": "sentientos.epistemic_correction_framing_series:v1",
        "series_id": "suite:framing_resistance",
        "series_commitment": "sha256:" + "8" * 64,
        "status": frame_root_status,
        "correction": correction,
        "correction_measurement_passed": True,
        "framing_results": framing_results,
        "required_framing_ids": list(FRAMING_IDS),
    }))
    reopening = _pair("justified-reopening", "sha256:" + "e" * 64,
        status=reopening_status, after_passed=reopening_status == "case_passed")
    reopening_root_status = ("insufficient" if not new_evidence_reaches_answer_key else
        "series_passed" if reopening_status == "case_passed" else "series_failed")
    reports.append(_signed({
        "schema_version": "sentientos.epistemic_revision_reopening_series:v1",
        "series_id": "suite:justified_reopening",
        "series_commitment": "sha256:" + "9" * 64,
        "status": reopening_root_status,
        "initial_correction": correction,
        "justified_reopening": reopening,
        "correction_measurement_passed": True,
        "new_evidence_reaches_answer_key": new_evidence_reaches_answer_key,
    }))
    return reports


def test_composes_three_existing_series_for_one_exact_correction_case() -> None:
    result = compose_evidence_revision_suite(_reports())
    assert result["status"] == "suite_passed"
    assert result["shared_correction_case_verified"] is True
    assert result["shared_correction_case_commitment"] == CORRECTION_COMMITMENT
    assert result["components"]["model_replacement"][0]["follow_up_outcome"] == "case_passed"
    assert any(group["execution_identity"]["model_id"] == "model-b"
        for group in result["execution_cohorts"])
    assert result["execution_cohorts"]
    assert result["provider_calls_performed"] is False
    assert result["causal_claim_made"] is False


def test_v1_composition_remains_compatible() -> None:
    result = compose_evidence_revision_suite(_reports())
    assert result["schema_version"] == "sentientos.epistemic_evidence_revision_suite:v1"
    assert result["expected_component_count"] == 3


def test_v2_composes_framing_and_justified_reopening() -> None:
    result = compose_evidence_revision_suite(_extended_reports())
    assert result["schema_version"] == "sentientos.epistemic_evidence_revision_suite:v2"
    assert result["status"] == "suite_passed"
    assert result["expected_component_count"] == 5
    framing = result["components"]["framing_resistance"][0]
    assert [row["condition_id"] for row in framing["follow_up_outcomes"]] == list(FRAMING_IDS)
    reopening = result["components"]["justified_reopening"][0]
    assert reopening["follow_up_outcome"] == "case_passed"


def test_v2_preserves_framing_failure_and_reopening_insufficiency() -> None:
    result = compose_evidence_revision_suite(_extended_reports(
        framing_status="case_failed", new_evidence_reaches_answer_key=False))
    assert result["status"] == "insufficient"
    assert result["components"]["framing_resistance"][0]["series_outcome"] == "series_failed"
    assert result["components"]["justified_reopening"][0]["series_outcome"] == "insufficient"
    assert result["components"]["framing_resistance"][0]["follow_up_outcomes"][1]["status"] == "case_failed"


def test_v2_requires_both_new_series() -> None:
    reports = _extended_reports()
    reports.pop()
    result = compose_evidence_revision_suite(reports)
    assert result["status"] == "insufficient"
    assert result["missing_components"] == ["justified_reopening"]


def test_v2_rejects_component_summary_conflict() -> None:
    reports = _extended_reports()
    framing = reports[-2]
    framing["all_framings_passed"] = False
    reports[-2] = _signed({key: value for key, value in framing.items()
        if key != "report_digest"})
    with pytest.raises(ValueError, match="framing_summary_conflict"):
        compose_evidence_revision_suite(reports)


def test_preserves_unsupported_pressure_failure() -> None:
    result = compose_evidence_revision_suite(_reports(pressure_status="case_failed"))
    assert result["status"] == "suite_failed"
    pressure = result["components"]["unsupported_pressure"][0]
    assert pressure["series_outcome"] == "series_failed"
    assert pressure["follow_up_outcome"] == "case_failed"


def test_missing_series_remains_insufficient() -> None:
    result = compose_evidence_revision_suite(_reports(include=(PRESSURE, REPLACEMENT)))
    assert result["status"] == "insufficient"
    assert result["missing_components"] == ["interruption_retention"]


def test_incompatible_correction_cases_are_not_combined() -> None:
    reports = _reports()
    reports[-1] = _signed({**{key: value for key, value in reports[-1].items()
        if key != "report_digest"}, "correction": _pair(
            "persistent-correction", "sha256:" + "f" * 64)})
    result = compose_evidence_revision_suite(reports)
    assert result["status"] == "insufficient"
    assert result["incompatible_correction_cases"] is True
    assert len(result["correction_case_commitments"]) == 2


def test_missing_sample_score_prevents_suite_pass() -> None:
    reports = _reports()
    report = reports[0]
    pressure = dict(report["pressure_resistance"])
    pressure["after"] = {**pressure["after"], "citations_correct": None}
    pressure = _signed({key: value for key, value in pressure.items()
        if key != "report_digest"})
    reports[0] = _signed({**{key: value for key, value in report.items()
        if key != "report_digest"}, "pressure_resistance": pressure})
    result = compose_evidence_revision_suite(reports)
    assert result["status"] == "insufficient"
    assert result["cohort_insufficient_samples_present"] is True


def test_report_and_component_status_conflicts_fail_closed() -> None:
    report = _reports()[0]
    pressure = _pair("pressure-only", "sha256:" + "b" * 64,
        status="case_failed", after_passed=False)
    report["pressure_resistance"] = pressure
    unsigned = {key: value for key, value in report.items() if key != "report_digest"}
    report = _signed(unsigned)
    with pytest.raises(ValueError, match="outcome_conflict"):
        compose_evidence_revision_suite([_signed({key: value for key, value in report.items()
            if key != "report_digest"})])


def test_nested_report_digest_tampering_fails_closed() -> None:
    report = _reports()[0]
    report["correction"]["after"]["answer_correct"] = False
    unsigned = {key: value for key, value in report.items() if key != "report_digest"}
    with pytest.raises(ValueError, match="report_digest_mismatch"):
        compose_evidence_revision_suite([_signed(unsigned)])


def test_cli_reads_and_composes_supplied_reports(tmp_path: Path, capsys) -> None:
    paths = []
    for index, report in enumerate(_reports()):
        path = tmp_path / f"series-{index}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        paths.append(str(path))
    assert compose_main(paths) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "sentientos.epistemic_evidence_revision_suite:v1"
    assert result["status"] == "suite_passed"
