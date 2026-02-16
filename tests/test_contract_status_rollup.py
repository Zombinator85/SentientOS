from __future__ import annotations

import json
from pathlib import Path

from scripts.contract_drift import main as contract_drift_main
from scripts.emit_contract_status import emit_contract_status


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def test_emit_contract_status_handles_missing_baselines(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    output = tmp_path / "glow" / "contracts" / "contract_status.json"
    payload = emit_contract_status(output)

    by_domain = {entry["domain_name"]: entry for entry in payload["contracts"]}
    assert by_domain["audits"]["drift_type"] == "baseline_missing"
    assert by_domain["pulse"]["drift_type"] == "baseline_missing"
    assert by_domain["self_model"]["drift_type"] == "baseline_missing"
    assert by_domain["federation_identity"]["drift_type"] == "baseline_missing"
    assert by_domain["vow_manifest"]["drift_type"] == "none"


def test_emit_contract_status_ingests_minimal_baseline_and_drift(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    _write_json(
        tmp_path / "glow" / "pulse" / "baseline" / "pulse_schema_baseline.json",
        {
            "schema_version": 1,
            "schema": {},
            "schema_fingerprint": "abc",
            "provenance": {
                "captured_at": "2026-01-01T00:00:00Z",
                "captured_by": "deadbeef",
                "tool_version": "1",
            },
        },
    )
    _write_json(
        tmp_path / "glow" / "pulse" / "pulse_schema_drift_report.json",
        {
            "drifted": True,
            "drift_type": "schema_only",
            "explanation": "Pulse fields changed.",
            "fingerprint_changed": False,
            "tuple_diff_detected": True,
        },
    )

    payload = emit_contract_status(tmp_path / "glow" / "contracts" / "contract_status.json")
    pulse = next(item for item in payload["contracts"] if item["domain_name"] == "pulse")

    assert pulse["baseline_present"] is True
    assert pulse["drifted"] is True
    assert pulse["drift_type"] == "schema_only"
    assert pulse["drift_explanation"] == "Pulse fields changed."
    assert pulse["fingerprint_changed"] is False
    assert pulse["tuple_diff_detected"] is True
    assert pulse["captured_by"] == "deadbeef"
    assert pulse["captured_at"] == "2026-01-01T00:00:00Z"
    assert pulse["tool_version"] == "1"


def test_contract_drift_strict_fails_when_any_drift_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    _write_json(
        tmp_path / "glow" / "pulse" / "baseline" / "pulse_schema_baseline.json",
        {"schema": {}, "schema_fingerprint": "abc"},
    )
    _write_json(
        tmp_path / "glow" / "pulse" / "pulse_schema_drift_report.json",
        {"drifted": True, "drift_type": "schema_only", "explanation": "fixture drift"},
    )

    monkeypatch.setenv("STRICT", "1")
    rc = contract_drift_main(["--from-existing-reports"])
    assert rc == 1
