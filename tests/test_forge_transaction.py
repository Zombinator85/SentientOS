from __future__ import annotations

import json
from pathlib import Path

from sentientos.forge_transaction import TransactionPolicy, TransactionSnapshot, capture_snapshot, compare_snapshots


def _snap(*, passed: bool, failed_count: int, drift: bool) -> TransactionSnapshot:
    return TransactionSnapshot(
        git_sha="abc",
        ci_baseline={"passed": passed, "failed_count": failed_count},
        contract_status_digest={"has_drift": drift, "drift_domains": []},
        timestamp="2026-01-01T00:00:00Z",
    )


def test_compare_detects_pass_to_fail() -> None:
    regressed, reasons, improved, _ = compare_snapshots(_snap(passed=True, failed_count=0, drift=False), _snap(passed=False, failed_count=1, drift=False))
    assert regressed is True
    assert "ci_baseline_pass_to_fail" in reasons
    assert improved is False


def test_compare_detects_failed_count_increase() -> None:
    regressed, reasons, _, _ = compare_snapshots(_snap(passed=False, failed_count=2, drift=False), _snap(passed=False, failed_count=3, drift=False))
    assert regressed is True
    assert "ci_baseline_failed_count_increase" in reasons


def test_compare_detects_drift_appearance() -> None:
    regressed, reasons, _, _ = compare_snapshots(_snap(passed=False, failed_count=2, drift=False), _snap(passed=False, failed_count=2, drift=True))
    assert regressed is True
    assert "contract_drift_appeared" in reasons


def test_compare_detects_improvement() -> None:
    regressed, reasons, improved, summary = compare_snapshots(_snap(passed=False, failed_count=4, drift=False), _snap(passed=False, failed_count=1, drift=False), policy=TransactionPolicy())
    assert regressed is False
    assert reasons == []
    assert improved is True
    assert "4->1" in summary


def test_capture_snapshot_includes_contract_alert_semantics_and_compat_fields(tmp_path: Path) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text(json.dumps({"passed": False, "failed_count": 2}), encoding="utf-8")
    (tmp_path / "glow/contracts/contract_status.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00Z",
                "contracts": [
                    {
                        "domain_name": "audits",
                        "baseline_present": True,
                        "drifted": True,
                        "drift_type": "required_keys_changed",
                        "drift_explanation": "required keys diverged",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = capture_snapshot(tmp_path, tmp_path)
    digest = snapshot.contract_status_digest
    assert digest["has_drift"] is True
    assert digest["drift_domains"] == ["audits"]
    assert digest["contract_alert_badge"] == "domain_drift"
    assert digest["contract_alert_reason"] == "domain_drift_rows_present"
    assert digest["contract_alert_counts"]["domain_drift"] == 1
    assert digest["contract_alert_counts"]["freshness_issue"] == 0


def test_capture_snapshot_keeps_freshness_distinct_from_domain_posture(tmp_path: Path) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text(json.dumps({"passed": True, "failed_count": 0}), encoding="utf-8")

    stale_status = {
        "pointer_state": "stale",
        "contracts": [
            {
                "domain_name": "pulse",
                "baseline_present": True,
                "drifted": False,
                "drift_type": "none",
            }
        ],
    }
    (tmp_path / "glow/contracts/contract_status.json").write_text(json.dumps(stale_status), encoding="utf-8")
    stale_snapshot = capture_snapshot(tmp_path, tmp_path)
    stale_digest = stale_snapshot.contract_status_digest
    assert stale_digest["contract_alert_badge"] == "freshness_issue"
    assert stale_digest["contract_alert_counts"]["freshness_issue"] == 1
    assert stale_digest["contract_alert_counts"]["domain_drift"] == 0

    drifted_status = {
        "pointer_state": "current",
        "contracts": [
            {
                "domain_name": "pulse",
                "baseline_present": True,
                "drifted": True,
                "drift_type": "schema_only",
            }
        ],
    }
    (tmp_path / "glow/contracts/contract_status.json").write_text(json.dumps(drifted_status), encoding="utf-8")
    drifted_snapshot = capture_snapshot(tmp_path, tmp_path)
    drifted_digest = drifted_snapshot.contract_status_digest
    assert drifted_digest["contract_alert_badge"] == "domain_drift"
    assert drifted_digest["contract_alert_counts"]["domain_drift"] == 1
    assert drifted_digest["contract_alert_counts"]["freshness_issue"] == 0


def test_capture_snapshot_keeps_baseline_missing_distinct_from_drift(tmp_path: Path) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text(json.dumps({"passed": True, "failed_count": 0}), encoding="utf-8")
    (tmp_path / "glow/contracts/contract_status.json").write_text(
        json.dumps(
            {
                "contracts": [
                    {
                        "domain_name": "self_model",
                        "baseline_present": False,
                        "drifted": None,
                        "drift_type": "baseline_missing",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = capture_snapshot(tmp_path, tmp_path)
    digest = snapshot.contract_status_digest
    assert digest["contract_alert_badge"] == "baseline_absent"
    assert digest["contract_alert_counts"]["baseline_absent"] == 1
    assert digest["contract_alert_counts"]["domain_drift"] == 0
    assert digest["has_drift"] is False
