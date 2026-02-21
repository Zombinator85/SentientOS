from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

from sentientos import forge
from sentientos.event_stream import FORGE_EVENTS_PATH, record_forge_event
from sentientos.forge_index import rebuild_index
from sentientos.forge_status import compute_status


def _write_jsonl(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_rebuild_index_counts_corrupt_lines(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "pulse/forge_queue.jsonl",
        [
            '{"request_id":"r1","goal":"forge_smoke_noop","priority":1,"requested_at":"2026-01-01T00:00:00Z"}',
            "{not-json}",
        ],
    )
    _write_jsonl(
        tmp_path / "pulse/forge_receipts.jsonl",
        [
            '{"request_id":"r2","status":"success","finished_at":"2026-01-01T01:00:00Z","publish_pr_url":"https://github.com/o/r/pull/2","publish_checks_overall":"failure"}',
            "[]",
        ],
    )
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text('{"passed":true}\n', encoding="utf-8")

    payload = rebuild_index(tmp_path)

    corrupt = payload["corrupt_count"]
    assert "sentinel_enabled" in payload
    assert "sentinel_state" in payload
    assert corrupt["queue"] == 1
    assert corrupt["receipts"] == 1
    assert corrupt["total"] == 2
    assert payload["latest_prs"]
    assert payload["latest_check_failures"]
    assert "merge_train" in payload


def test_compute_status_reads_lock_and_budgets(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write_jsonl(
        tmp_path / "pulse/forge_receipts.jsonl",
        [
            '{"request_id":"r1","status":"success","finished_at":"2099-01-01T00:00:00Z","report_path":"glow/forge/report_future.json"}',
            '{"request_id":"r2","status":"failed","finished_at":"2099-01-01T00:10:00Z"}',
        ],
    )
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/report_future.json").write_text('{"baseline_budget":{"total_files_changed":7}}\n', encoding="utf-8")
    (tmp_path / ".forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".forge/forge.lock").write_text(
        json.dumps({"request_id": "r3", "goal": "forge_smoke_noop", "started_at": "2099-01-01T00:00:00Z", "pid": 1234}),
        encoding="utf-8",
    )

    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_RUNS_PER_DAY", "5")
    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_RUNS_PER_HOUR", "3")
    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_FILES_CHANGED_PER_DAY", "20")

    status = compute_status(tmp_path)

    assert status.daemon_enabled is True
    assert status.lock_owner_pid == 1234
    assert status.current_request_id == "r3"
    assert status.current_goal == "forge_smoke_noop"
    assert status.runs_remaining_day >= 0
    assert status.runs_remaining_hour >= 0
    assert status.files_remaining_day >= 0
    assert isinstance(status.sentinel_enabled, bool)
    assert isinstance(status.train_enabled, bool)


def test_cli_status_and_index(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    _write_jsonl(tmp_path / "pulse/forge_queue.jsonl", ['{"request_id":"r1","goal":"forge_smoke_noop"}'])

    assert forge.main(["status"]) == 0
    assert forge.main(["index"]) == 0


def test_event_emission_writes_jsonl(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    record_forge_event({"event": "forge_test", "status": "ok", "request_id": "r1", "goal_id": "forge_smoke_noop"})
    lines = FORGE_EVENTS_PATH.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert payload["event"] == "forge_test"
    assert payload["request_id"] == "r1"


def test_gui_smoke_import_registers_forge_panel(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake_priv = types.ModuleType("sentientos.privilege")
    fake_priv.require_admin_banner = lambda: None
    fake_priv.require_lumos_approval = lambda: None
    monkeypatch.setitem(sys.modules, "sentientos.privilege", fake_priv)

    module = importlib.import_module("gui.cathedral_gui")
    assert module.forge_panel_registered() is True


def test_index_includes_quarantines(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "glow/forge/quarantine_2026-01-01T00-00-00Z.json").write_text('{"quarantine_ref":"quarantine/forge-1","reasons":["no_progress"]}\n', encoding="utf-8")

    payload = rebuild_index(tmp_path)

    assert "latest_quarantines" in payload
    assert payload["latest_quarantines"]


def test_index_computes_progress_trend_and_stagnation(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")

    for idx in range(3):
        payload = {
            "provenance_run_id": f"run-{idx}",
            "generated_at": f"2026-01-01T00:0{idx}:00Z",
            "goal_id": "repo_green_storm",
            "ci_baseline_before": {"failed_count": 5},
            "ci_baseline_after": {"failed_count": 5},
            "baseline_progress": [{"delta": {"improved": False}}],
        }
        (tmp_path / f"glow/forge/report_2026-01-01T00-0{idx}-00Z.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    payload = rebuild_index(tmp_path)

    trend = payload.get("progress_trend", [])
    assert len(trend) == 3
    assert payload.get("stagnation_alert") is True


def test_index_includes_progress_contract_snapshot(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "glow/contracts/forge_progress_baseline.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "git_sha": "abc",
                "window_size": 10,
                "last_runs": [],
                "stagnation_alert": False,
                "stagnation_reason": None,
                "last_improving_run_id": None,
                "last_stagnant_run_id": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = rebuild_index(tmp_path)

    assert "forge_progress_contract_latest" in payload
    assert isinstance(payload["forge_progress_contract_latest"], dict)


def test_index_includes_audit_integrity_summary_and_doctor_reports(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": False, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/audit_doctor_20260101T000000Z.json").write_text('{"status":"repaired"}\n', encoding="utf-8")
    (tmp_path / "glow/forge/audit_docket_20260101T000000Z.json").write_text('{"kind":"audit_docket"}\n', encoding="utf-8")

    payload = rebuild_index(tmp_path)

    assert payload["latest_audit_doctor_reports"]
    assert isinstance(payload.get("audit_integrity_status"), dict)
    assert payload["audit_integrity_status"]["runtime_ok"] is False


def test_index_includes_remote_doctrine_fetch_extended_fields(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    _write_jsonl(
        tmp_path / "glow/forge/remote_doctrine_fetches.jsonl",
        [
            json.dumps(
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "pr_number": 7,
                    "sha": "abc",
                    "source": "remote",
                    "selected_via": "api:run-artifacts",
                    "artifact_created_at": "2026-01-01T00:00:00Z",
                    "errors": ["metadata_mismatch:sha"],
                    "metadata_sha": "def",
                    "metadata_ok": False,
                    "manifest_ok": False,
                    "bundle_sha256": "1234abcd",
                    "failing_hash_paths": ["contract_status.json"],
                    "mirror_used": True,
                },
                sort_keys=True,
            )
        ],
    )

    payload = rebuild_index(tmp_path)

    rows = payload.get("remote_doctrine_fetches", [])
    assert rows
    row = rows[-1]
    assert row["selected_via"] == "api:run-artifacts"
    assert row["artifact_created_at"] == "2026-01-01T00:00:00Z"
    assert row["metadata_ok"] is False
    assert row["manifest_ok"] is False
    assert row["bundle_sha256"] == "1234abcd"
    assert row["failing_hash_paths"] == ["contract_status.json"]
    assert row["mirror_used"] is True


def test_index_includes_merge_receipt_summary(tmp_path: Path) -> None:
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_2026.json").write_text(
        json.dumps(
            {
                "pr_url": "https://github.com/o/r/pull/9",
                "head_sha": "abc",
                "doctrine_source": "remote",
                "doctrine_identity": {"bundle_sha256": "1234567890abcdef1234"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)

    payload = rebuild_index(tmp_path)

    assert payload["last_merge_receipt"]["pr"] == "https://github.com/o/r/pull/9"
    assert payload["last_merged_doctrine_bundle_sha256"] == "1234567890abcdef"


def test_index_includes_receipt_chain_status_fields(tmp_path: Path) -> None:
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 2,
        "receipt_id": "2026-01-01T00-00-00Z-pr9-abc",
        "created_at": "2026-01-01T00:00:00Z",
        "pr_url": "https://github.com/o/r/pull/9",
        "pr_number": 9,
        "head_sha": "abc",
        "base_branch": "main",
        "doctrine_identity": {"bundle_sha256": "1234567890abcdef1234", "selected_via": "api", "mirror_used": False, "metadata_ok": True, "manifest_ok": True},
        "gating_result": "merged",
        "gating_reason": "ok",
        "prev_receipt_hash": None,
    }
    from sentientos.receipt_chain import compute_receipt_hash

    receipt["receipt_hash"] = compute_receipt_hash({k: v for k, v in receipt.items() if k != "receipt_hash"})
    (tmp_path / "glow/forge/receipts/merge_receipt_2026-01-01T00-00-00Z-pr9-abc.json").write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")

    payload = rebuild_index(tmp_path)

    assert payload["receipt_chain_status"] == "ok"
    assert payload["last_receipt_hash"]
    assert "receipt_chain_checked_at" in payload


def test_index_includes_anchor_status_fields(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_ANCHOR_SIGNING", "hmac-test")
    from sentientos.receipt_chain import append_receipt
    from sentientos.receipt_anchors import create_anchor

    append_receipt(
        tmp_path,
        {
            "schema_version": 2,
            "receipt_id": "2026-01-01T00-00-00Z-pr9-abc",
            "created_at": "2026-01-01T00:00:00Z",
            "pr_url": "https://github.com/o/r/pull/9",
            "pr_number": 9,
            "head_sha": "abc",
            "base_branch": "main",
            "doctrine_identity": {"bundle_sha256": "1234567890abcdef1234", "selected_via": "api", "mirror_used": False, "metadata_ok": True, "manifest_ok": True},
            "gating_result": "merged",
            "gating_reason": "ok",
        },
    )
    create_anchor(tmp_path)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")

    payload = rebuild_index(tmp_path)

    assert payload["anchor_status"] == "ok"
    assert payload["last_anchor_id"]
    assert payload["last_anchor_tip_hash"]
    assert payload["last_anchor_public_key_id"]
    assert payload["anchor_checked_at"]
    assert payload["federation_integrity_status"] in {"unknown", "ok", "diverged"}
    assert payload["witness_status"] in {"ok", "failed", "disabled"}


def test_index_includes_audit_chain_summary_fields(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "glow/forge/audit_reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/audit_reports/audit_chain_report_20260101T000000Z.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "created_at": "2026-01-01T00:00:00Z",
                "status": "broken",
                "break_count": 1,
                "first_break": {
                    "path": "logs/audit.jsonl",
                    "line_number": 1,
                    "expected_prev_hash": "0" * 64,
                    "found_prev_hash": "deadbeef",
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = rebuild_index(tmp_path)

    assert payload["schema_version"] == 12
    assert payload["audit_chain_status"] == "broken"
    assert payload["last_audit_chain_report_path"] == "glow/forge/audit_reports/audit_chain_report_20260101T000000Z.json"

def test_index_includes_integrity_pressure_fields(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    _write_jsonl(
        tmp_path / "pulse/integrity_incidents.jsonl",
        [
            json.dumps(
                {
                    "created_at": "2099-01-01T00:00:00Z",
                    "enforcement_mode": "enforce",
                    "triggers": ["receipt_chain_broken"],
                    "quarantine_activated": True,
                },
                sort_keys=True,
            )
        ],
    )

    payload = rebuild_index(tmp_path)

    assert payload["integrity_pressure_level"] >= 0
    assert payload["strategic_posture"] in {"stability", "balanced", "velocity"}
    assert isinstance(payload.get("derived_thresholds"), dict)
    assert "posture_last_changed_at" in payload
    assert payload["incidents_last_24h"] == 1
    assert payload["enforced_failures_last_24h"] == 1
    assert payload["quarantine_activations_last_24h"] == 1
    assert isinstance(payload.get("integrity_pressure_metrics"), dict)


def test_index_reads_mypy_ratchet_status_from_forge_path(tmp_path: Path) -> None:
    (tmp_path / "glow/forge/ratchets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "glow/forge/ratchets/mypy_ratchet_status.json").write_text(
        json.dumps({"status": "new_errors", "new_error_count": 3}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    payload = rebuild_index(tmp_path)

    assert payload["mypy_status"] == "new_errors"
    assert payload["mypy_new_error_count"] == 3
