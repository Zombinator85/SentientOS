from __future__ import annotations

from sentientos.forge_outcomes import summarize_report


def test_summarize_report_tolerates_missing_fields() -> None:
    summary = summarize_report({"goal_id": "repo_green_storm", "outcome": "failed"})

    assert summary.goal_id == "repo_green_storm"
    assert summary.ci_before_failed_count is None
    assert summary.ci_after_failed_count is None
    assert summary.last_progress_improved is False
    assert summary.no_improvement_streak == 0


def test_summarize_report_derives_last_progress_improved() -> None:
    summary = summarize_report(
        {
            "goal_id": "repo_green_storm",
            "ci_baseline_before": {"failed_count": 8},
            "ci_baseline_after": {"failed_count": 8},
            "baseline_progress": [
                {
                    "iteration": 2,
                    "delta": {"improved": False, "notes": ["no_outcome_improvement"]},
                    "notes": ["confirm_full_rerun"],
                }
            ],
        }
    )

    assert summary.last_progress_improved is False
    assert summary.no_improvement_streak == 1
    assert "no_outcome_improvement" in summary.last_progress_notes


def test_summarize_report_reads_enriched_contract_digest() -> None:
    summary = summarize_report(
        {
            "transaction_snapshot_after": {
                "contract_status_digest": {
                    "has_drift": False,
                    "drift_domains": [],
                    "contract_alert_badge": "freshness_issue",
                    "contract_alert_reason": "rows_not_current",
                    "contract_alert_counts": {
                        "freshness_issue": 1,
                        "domain_drift": 0,
                        "baseline_absent": 0,
                        "partial_evidence": 0,
                        "informational": 0,
                    },
                    "contract_row_summary_counts": {
                        "row_count": 1,
                        "drifted_rows": 0,
                        "baseline_missing_rows": 0,
                        "indeterminate_rows": 0,
                        "stale_or_missing_rows": 1,
                    },
                }
            }
        }
    )

    assert summary.has_contract_drift is False
    assert summary.contract_alert_badge == "freshness_issue"
    assert summary.contract_alert_reason == "rows_not_current"
    assert summary.contract_alert_counts["freshness_issue"] == 1
    assert summary.contract_row_summary_counts["stale_or_missing_rows"] == 1
