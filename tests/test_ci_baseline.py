from __future__ import annotations

import json
from pathlib import Path

from scripts.emit_ci_baseline import main as emit_ci_baseline_main
from scripts.emit_contract_status import emit_contract_status
from sentientos.ci_baseline import evaluate_ci_baseline_drift
from sentientos.forge_failures import semantic_failure_signature


def test_emit_ci_baseline_writes_schema_and_contract_rollup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args, **kwargs):
        class _Proc:
            returncode = 1
            stdout = "FAILED tests/test_alpha.py::test_one - AssertionError: boom\n= 1 failed in 0.10s ="
            stderr = ""

        return _Proc()

    monkeypatch.setattr("sentientos.ci_baseline.subprocess.run", fake_run)

    rc = emit_ci_baseline_main([])
    assert rc == 0

    payload = json.loads((tmp_path / "glow" / "contracts" / "ci_baseline.json").read_text(encoding="utf-8"))
    assert payload["runner"] == "scripts.run_tests"
    assert payload["failed_count"] == 1
    assert payload["passed"] is False
    assert payload["top_clusters"]

    status = emit_contract_status(tmp_path / "glow" / "contracts" / "contract_status.json")
    ci_domain = next(item for item in status["contracts"] if item["domain_name"] == "ci_baseline")
    assert ci_domain["failed_count"] == 1
    assert ci_domain["drifted"] is True


def _sig(node: str, message: str, count: int = 1):
    return {"signature": semantic_failure_signature(node, "AssertionError", message), "nodeid": node, "count": count}


def _snapshot(failures):
    return {"passed": not failures, "failed_count": sum(row["count"] for row in failures), "failure_signatures": failures, "failure_signatures_complete": True}


def test_ci_baseline_compares_failure_identity_and_multiplicity() -> None:
    a, b = _sig("tests/test_a.py::test_a", "A"), _sig("tests/test_b.py::test_b", "B")
    same_count_changed_identity = evaluate_ci_baseline_drift(_snapshot([b]), previous_payload=_snapshot([a]))
    assert same_count_changed_identity.drifted is True
    assert same_count_changed_identity.drift_type == "failure_signature_regression"
    assert same_count_changed_identity.repository_health_status == "red"

    net_zero = evaluate_ci_baseline_drift(_snapshot([a, b]), previous_payload=_snapshot([_sig("tests/test_old.py::test_old", "old"), a]))
    assert net_zero.drift_type == "failure_signature_regression"
    assert net_zero.new_failures and net_zero.retired_failures

    increased = evaluate_ci_baseline_drift(_snapshot([_sig("tests/test_a.py::test_a", "A", 2)]), previous_payload=_snapshot([a]))
    assert increased.drift_type == "failure_signature_regression"
    assert increased.new_failures[0]["count"] == 1


def test_matching_failure_multiset_is_preexisting_debt_but_health_stays_red() -> None:
    failure = _sig("tests/test_a.py::test_a", "A")
    drift = evaluate_ci_baseline_drift(_snapshot([failure]), previous_payload=_snapshot([failure]))
    assert drift.drifted is False
    assert drift.drift_type == "matched_preexisting_debt"
    assert drift.task_regression_status == "no_regression"
    assert drift.repository_health_status == "red"


def test_ci_baseline_fails_closed_without_signature_evidence() -> None:
    drift = evaluate_ci_baseline_drift({"passed": False, "failed_count": 5}, previous_payload={"passed": False, "failed_count": 5})
    assert drift.drifted is True
    assert drift.drift_type == "comparison_incomplete"
