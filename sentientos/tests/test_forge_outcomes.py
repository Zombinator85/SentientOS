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
