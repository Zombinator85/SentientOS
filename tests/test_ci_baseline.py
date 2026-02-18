from __future__ import annotations

import json
from pathlib import Path

from scripts.emit_ci_baseline import main as emit_ci_baseline_main
from scripts.emit_contract_status import emit_contract_status
from sentientos.ci_baseline import evaluate_ci_baseline_drift


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


def test_ci_baseline_drift_logic_thresholding() -> None:
    drift = evaluate_ci_baseline_drift({"passed": True, "failed_count": 2}, previous_payload={"failed_count": 1}, failure_threshold_delta=0)
    assert drift.drifted is True
    assert drift.drift_type == "failed_count_regression"

    clean = evaluate_ci_baseline_drift({"passed": True, "failed_count": 1}, previous_payload={"failed_count": 1}, failure_threshold_delta=0)
    assert clean.drifted is False

    failing = evaluate_ci_baseline_drift({"passed": False, "failed_count": 5})
    assert failing.drifted is True
    assert failing.drift_type == "tests_failing"
