from __future__ import annotations

from sentientos.forge_transaction import TransactionPolicy, TransactionSnapshot, compare_snapshots


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
