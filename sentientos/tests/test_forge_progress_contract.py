from __future__ import annotations

import json
from pathlib import Path

from scripts.emit_contract_status import emit_contract_status
from sentientos.forge_progress_contract import emit_forge_progress_contract


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_emit_progress_contract_stagnation_window(tmp_path: Path) -> None:
    for idx in range(3):
        _write_json(
            tmp_path / f"glow/forge/report_{idx}.json",
            {
                "provenance_run_id": f"run-{idx}",
                "generated_at": f"2026-01-01T00:0{idx}:00Z",
                "goal_id": "repo_green_storm",
                "ci_baseline_before": {"failed_count": 4},
                "ci_baseline_after": {"failed_count": 4},
                "baseline_progress": [{"delta": {"improved": False, "notes": ["still stuck"]}}],
            },
        )

    contract = emit_forge_progress_contract(tmp_path)

    assert contract.schema_version == 1
    assert len(contract.last_runs or []) == 3
    assert contract.stagnation_alert is True
    assert contract.stagnation_reason == "3 consecutive non-improving runs"
    assert contract.last_improving_run_id is None


def test_contract_status_includes_forge_progress_domain_non_noisy_drift(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    for idx in range(2):
        _write_json(
            tmp_path / f"glow/forge/report_{idx}.json",
            {
                "provenance_run_id": f"run-{idx}",
                "generated_at": f"2026-01-01T00:0{idx}:00Z",
                "goal_id": "repo_green_storm",
                "ci_baseline_before": {"failed_count": 5},
                "ci_baseline_after": {"failed_count": 4 - idx},
                "baseline_progress": [{"delta": {"improved": True}}],
            },
        )

    first = emit_contract_status(tmp_path / "glow/contracts/contract_status.json")
    domain_first = next(item for item in first["contracts"] if item["domain_name"] == "forge_progress_baseline")
    assert domain_first["drifted"] is False

    _write_json(
        tmp_path / "glow/forge/report_3.json",
        {
            "provenance_run_id": "run-3",
            "generated_at": "2026-01-01T00:03:00Z",
            "goal_id": "repo_green_storm",
            "ci_baseline_before": {"failed_count": 3},
            "ci_baseline_after": {"failed_count": 2},
            "baseline_progress": [{"delta": {"improved": True}}],
        },
    )
    second = emit_contract_status(tmp_path / "glow/contracts/contract_status.json")
    domain_second = next(item for item in second["contracts"] if item["domain_name"] == "forge_progress_baseline")
    assert domain_second["drifted"] is False
