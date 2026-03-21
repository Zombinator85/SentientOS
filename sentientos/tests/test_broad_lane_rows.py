from __future__ import annotations

from sentientos.broad_lane_rows import rows_from_broad_lane_summary


def test_rows_from_summary_prefers_explicit_lane_rows_and_normalizes_shape() -> None:
    rows = rows_from_broad_lane_summary(
        {
            "schema_version": 1,
            "lane_rows": [
                {
                    "lane": "run_tests",
                    "status": "amber",
                    "lane_state": "lane_completed_with_deferred_debt",
                    "pointer_state": "current",
                    "primary_artifact_path": "glow/test_runs/test_run_provenance.json",
                    "supporting_artifact_paths": ["glow/test_runs/test_failure_digest.json"],
                    "created_at": "2026-03-20T01:00:00Z",
                    "run_id": "run-1",
                    "digest_sha256": "abc123",
                    "provenance_resolution": {"mode": "glob+single"},
                    "why_latest": "ordered by created_at",
                    "freshness_hours": 24,
                    "failure_count": 2,
                    "details": {"failure_group_count": 2},
                }
            ],
        }
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["lane"] == "run_tests"
    assert row["pointer_state"] == "current"
    assert row["lane_state"] == "lane_completed_with_deferred_debt"
    assert row["policy_meaning"] == "deferred"
    assert row["summary_reason"] == "pointer=current; lane=lane_completed_with_deferred_debt; policy=deferred"
    assert row["supporting_artifact_paths"] == ["glow/test_runs/test_failure_digest.json"]
    assert row["digest_sha256"] == "abc123"
