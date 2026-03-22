from __future__ import annotations

from sentientos.forge_transaction import TransactionSnapshot, build_contract_status_digest, compare_snapshots, snapshot_to_report_dict


def test_contract_digest_separates_stale_from_drift() -> None:
    stale_healthy = build_contract_status_digest(
        {
            "pointer_state": "stale",
            "contracts": [
                {"domain_name": "ci_baseline", "baseline_present": True, "drifted": False, "drift_type": "none"}
            ],
        }
    )
    current_drifted = build_contract_status_digest(
        {
            "pointer_state": "current",
            "contracts": [
                {"domain_name": "ci_baseline", "baseline_present": True, "drifted": True, "drift_type": "content_mismatch"}
            ],
        }
    )
    baseline_missing = build_contract_status_digest(
        {
            "pointer_state": "current",
            "contracts": [
                {"domain_name": "ci_baseline", "baseline_present": False, "drifted": None, "drift_type": "baseline_missing"}
            ],
        }
    )

    assert stale_healthy["contract_alert_badge"] == "freshness_issue"
    assert stale_healthy["contract_alert_counts"]["freshness_issue"] == 1
    assert stale_healthy["has_drift"] is False

    assert current_drifted["contract_alert_badge"] == "domain_drift"
    assert current_drifted["contract_alert_counts"]["domain_drift"] == 1
    assert current_drifted["has_drift"] is True

    assert baseline_missing["contract_alert_badge"] == "baseline_absent"
    assert baseline_missing["contract_alert_counts"]["baseline_absent"] == 1
    assert baseline_missing["has_drift"] is False


def test_compare_snapshots_regression_doctrine_unchanged() -> None:
    before = TransactionSnapshot(
        git_sha="a",
        ci_baseline={"passed": True, "failed_count": 0},
        contract_status_digest={"has_drift": False, "drift_domains": []},
        timestamp="2026-01-01T00:00:00Z",
    )
    after = TransactionSnapshot(
        git_sha="b",
        ci_baseline={"passed": True, "failed_count": 0},
        contract_status_digest={
            "has_drift": True,
            "drift_domains": ["ci_baseline"],
            "contract_alert_badge": "domain_drift",
            "contract_alert_reason": "domain_drift_rows_present",
        },
        timestamp="2026-01-01T00:10:00Z",
    )

    regressed, reasons, _improved, _summary = compare_snapshots(before, after)

    assert regressed is True
    assert "contract_drift_appeared" in reasons


def test_snapshot_to_report_dict_carries_digest() -> None:
    snapshot = TransactionSnapshot(
        git_sha="abc",
        ci_baseline={"passed": False, "failed_count": 3},
        contract_status_digest={"has_drift": False, "contract_alert_badge": "freshness_issue"},
        timestamp="2026-01-01T00:00:00Z",
    )

    payload = snapshot_to_report_dict(snapshot)

    assert payload is not None
    assert payload["contract_status_digest"]["contract_alert_badge"] == "freshness_issue"
    assert payload["ci_baseline"]["failed_count"] == 3
