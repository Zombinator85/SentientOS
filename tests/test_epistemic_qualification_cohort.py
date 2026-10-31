from __future__ import annotations

from typing import Any

import pytest

from sentientos.epistemic_qualification_cohort import summarize_qualification_reports
from sentientos.epistemic_qualification_execution_binding import build_execution_binding
from sentientos.local_model_authority import digest_payload

pytestmark = pytest.mark.no_legacy_skip


def _signed(value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "report_digest": "sha256:" + digest_payload(value)}


def _binding(condition: str, *, model: str | None = "model-a", config: str = "cfg-a",
        complete: bool = True) -> dict[str, Any]:
    return build_execution_binding(
        case_id="case-1", evaluator_version="rubric-v1", condition=condition,
        model_id=model, model_artifact_digest="sha256:artifact-a",
        active_model_identity={"worker": model}, generation_config={"name": config},
        prompt_digest="sha256:prompt", projection_digest="sha256:projection",
        observation_digest="sha256:observation", receipt_digest="sha256:receipt",
        output_digest="sha256:output" if complete else None)


def _sample(condition: str, *, model: str | None = "model-a", config: str = "cfg-a",
        passed: bool = True, complete: bool = True) -> dict[str, Any]:
    return {
        "execution_binding": _binding(condition, model=model, config=config,
            complete=complete),
        "measurement_status": "scored",
        "execution_status": "executed",
        "state_stance_correct": passed,
        "answer_correct": passed,
        "reason_code_correct": None,
        "citations_correct": passed,
    }


def _report(*, case_commitment: str = "sha256:" + "a" * 64,
        before_model: str = "model-a", after_model: str = "model-a",
        config: str = "cfg-a", status: str = "case_passed",
        after_passed: bool = True) -> dict[str, Any]:
    return _signed({
        "schema_version": "sentientos.epistemic_revision_case_result:v1",
        "case_id": "case-1", "case_commitment": case_commitment,
        "status": status,
        "before": _sample("before", model=before_model, config=config),
        "after": _sample("after", model=after_model, config=config,
            passed=after_passed),
    })


def test_groups_exact_case_and_execution_identity_and_preserves_scores() -> None:
    first = _report()
    second = _report(after_model="model-b", after_passed=False)
    result = summarize_qualification_reports([first, second])
    assert result["group_count"] == 2
    assert result["paired_result_count"] == 2
    by_model = {row["execution_identity"]["model_id"]: row
        for row in result["groups"]}
    assert by_model["model-a"]["sample_outcomes"] == {
        "scored_pass": 3, "scored_fail": 0, "insufficient": 0}
    assert by_model["model-b"]["sample_outcomes"]["scored_fail"] == 1
    assert result["real_model_qualification_established"] is False


def test_exact_case_commitment_and_generation_config_split_groups() -> None:
    result = summarize_qualification_reports([
        _report(),
        _report(case_commitment="sha256:" + "b" * 64),
        _report(config="cfg-b"),
    ])
    assert result["group_count"] == 3


def test_incomplete_pair_is_retained_as_insufficient() -> None:
    report = _report()
    report["before"] = _sample("before", model=None)
    unsigned = {key: value for key, value in report.items() if key != "report_digest"}
    report["report_digest"] = "sha256:" + digest_payload(unsigned)
    result = summarize_qualification_reports([report])
    assert len(result["unattributed_samples"]) == 1
    assert result["unattributed_samples"][0]["sample_outcome"] == "insufficient"
    assert result["groups"][0]["sample_outcomes"]["scored_pass"] == 1


def test_missing_score_is_insufficient_not_a_failure() -> None:
    report = _report()
    report["after"]["citations_correct"] = None
    unsigned = {key: value for key, value in report.items() if key != "report_digest"}
    report["report_digest"] = "sha256:" + digest_payload(unsigned)
    result = summarize_qualification_reports([report])
    after_group = next(row for row in result["groups"]
        if row["conditions"]["after"] == 1)
    assert after_group["sample_outcomes"]["insufficient"] == 1


def test_binding_cannot_be_reused_for_other_condition() -> None:
    report = _report()
    report["after"]["execution_binding"] = _binding("before")
    unsigned = {key: value for key, value in report.items() if key != "report_digest"}
    report["report_digest"] = "sha256:" + digest_payload(unsigned)
    with pytest.raises(ValueError, match="context_mismatch"):
        summarize_qualification_reports([report])


def test_missing_case_commitment_is_unattributed_and_insufficient() -> None:
    report = _report(case_commitment="missing")
    result = summarize_qualification_reports([report])
    assert len(result["unattributed_samples"]) == 2
    assert not result["groups"]


def test_tampered_report_and_binding_digests_fail_closed() -> None:
    report = _report()
    report["after"]["answer_correct"] = False
    with pytest.raises(ValueError, match="report_digest_mismatch"):
        summarize_qualification_reports([report])
    report = _report()
    report["before"]["execution_binding"]["model_id"] = "forged"
    unsigned = {key: value for key, value in report.items() if key != "report_digest"}
    report["report_digest"] = "sha256:" + digest_payload(unsigned)
    with pytest.raises(ValueError, match="binding_digest_mismatch"):
        summarize_qualification_reports([report])


def test_duplicate_report_digest_is_rejected() -> None:
    report = _report()
    with pytest.raises(ValueError, match="duplicate_report"):
        summarize_qualification_reports([report, report])
