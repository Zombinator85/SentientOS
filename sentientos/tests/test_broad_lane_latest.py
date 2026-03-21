from __future__ import annotations

import json
from pathlib import Path

from sentientos.observatory.broad_lane_latest import emit_broad_lane_latest_pointers


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_selects_latest_run_tests_snapshot_by_created_at_and_run_id(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "glow/test_runs/provenance/old.json",
        {"timestamp": "2026-03-20T00:00:00Z", "provenance_hash": "aaa", "execution_mode": "execute", "metrics_status": "ok", "pytest_exit_code": 0},
    )
    _write_json(
        tmp_path / "glow/test_runs/provenance/new.json",
        {"timestamp": "2026-03-20T01:00:00Z", "provenance_hash": "bbb", "execution_mode": "execute", "metrics_status": "ok", "pytest_exit_code": 0},
    )

    emit_broad_lane_latest_pointers(tmp_path)
    payload = json.loads((tmp_path / "glow/observatory/broad_lane/run_tests_latest_pointer.json").read_text(encoding="utf-8"))

    assert payload["primary_artifact_path"] == "glow/test_runs/provenance/new.json"
    assert payload["run_id"] == "bbb"


def test_selects_latest_mypy_pointer_and_marks_stale(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "glow/contracts/typing_ratchet_status.json",
        {"generated_at": "2020-01-01T00:00:00Z", "status": "ok", "deferred_debt_error_count": 0},
    )
    _write_json(
        tmp_path / "glow/forge/ratchets/mypy_ratchet_status.json",
        {"generated_at": "2020-01-01T00:00:00Z", "status": "ok", "deferred_debt_error_count": 0},
    )

    emit_broad_lane_latest_pointers(tmp_path)
    payload = json.loads((tmp_path / "glow/observatory/broad_lane/mypy_latest_pointer.json").read_text(encoding="utf-8"))

    assert payload["pointer_state"] == "stale"
    assert payload["primary_artifact_path"] == "glow/forge/ratchets/mypy_ratchet_status.json"


def test_classifies_unavailable_incomplete_and_missing_states(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "glow/test_runs/test_run_provenance.json",
        {"timestamp": "2026-03-20T01:00:00Z", "execution_mode": "execute", "metrics_status": "unavailable", "exit_reason": "airlock-failed"},
    )

    emit_broad_lane_latest_pointers(tmp_path)
    run_tests = json.loads((tmp_path / "glow/observatory/broad_lane/run_tests_latest_pointer.json").read_text(encoding="utf-8"))
    mypy = json.loads((tmp_path / "glow/observatory/broad_lane/mypy_latest_pointer.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "glow/observatory/broad_lane/broad_lane_latest_summary.json").read_text(encoding="utf-8"))

    assert run_tests["pointer_state"] == "unavailable"
    assert run_tests["lane_state"] == "lane_unavailable_in_environment"
    assert mypy["pointer_state"] == "missing"
    assert summary["pointer_state"] == "missing"


def test_marks_run_tests_incomplete_when_failure_digest_is_missing(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "glow/test_runs/test_run_provenance.json",
        {
            "timestamp": "2026-03-20T01:00:00Z",
            "execution_mode": "execute",
            "metrics_status": "ok",
            "pytest_exit_code": 1,
        },
    )

    emit_broad_lane_latest_pointers(tmp_path)
    payload = json.loads((tmp_path / "glow/observatory/broad_lane/run_tests_latest_pointer.json").read_text(encoding="utf-8"))

    assert payload["pointer_state"] == "incomplete"
    assert payload["lane_state"] == "lane_incomplete"
    assert payload["details"]["reason"] == "supporting_artifacts_missing"
