from __future__ import annotations

import json
from pathlib import Path

from scripts.analyze_test_provenance import Thresholds, _discover_inputs, analyze
from scripts.export_test_provenance_bundle import main as export_main
from scripts.provenance_hash_chain import HASH_ALGO, compute_provenance_hash


def _run(*, skip_rate: float, xfail_rate: float, executed: int, passed: int, intent: str = "default", budget_allow: bool = False) -> dict[str, object]:
    return {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "run_intent": intent,
        "skip_rate": skip_rate,
        "xfail_rate": xfail_rate,
        "tests_executed": executed,
        "tests_passed": passed,
        "budget_allow_violation": budget_allow,
    }


def _chain_payload(*, ts: str, source: Path, prev_hash: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "timestamp": ts,
        "run_intent": "default",
        "tests_executed": 10,
        "tests_passed": 10,
        "hash_algo": HASH_ALGO,
        "prev_provenance_hash": prev_hash,
    }
    payload["provenance_hash"] = compute_provenance_hash(payload, prev_hash)
    payload["_source"] = str(source)
    return payload


def _build_chain(tmp_path: Path, count: int = 3) -> list[dict[str, object]]:
    runs: list[dict[str, object]] = []
    prev_hash: str | None = None
    for idx in range(count):
        ts = f"2026-01-01T00:00:0{idx}+00:00"
        source = tmp_path / f"20260101T00000{idx}Z_deadbeef_{idx}.json"
        run = _chain_payload(ts=ts, source=source, prev_hash=prev_hash)
        prev_hash = str(run["provenance_hash"])
        runs.append(run)
    return runs


def test_analyze_no_alert_on_stable_runs() -> None:
    runs = [_run(skip_rate=0.05, xfail_rate=0.02, executed=100, passed=98) for _ in range(8)]

    report = analyze(
        runs,
        Thresholds(
            window_size=4,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
    )

    assert report["avoidance_alert"] is False
    assert report["avoidance_reasons"] == []


def test_analyze_alert_on_spikes_and_override() -> None:
    prior = [_run(skip_rate=0.02, xfail_rate=0.01, executed=200, passed=190) for _ in range(4)]
    current = [
        _run(skip_rate=0.25, xfail_rate=0.15, executed=80, passed=70, intent="exceptional", budget_allow=True),
        _run(skip_rate=0.24, xfail_rate=0.16, executed=80, passed=69, intent="exceptional"),
        _run(skip_rate=0.26, xfail_rate=0.14, executed=80, passed=71, intent="exceptional"),
        _run(skip_rate=0.23, xfail_rate=0.15, executed=80, passed=68),
    ]

    report = analyze(
        prior + current,
        Thresholds(
            window_size=4,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
    )

    assert report["avoidance_alert"] is True
    assert "skip_rate_spike" in report["avoidance_reasons"]
    assert "xfail_rate_spike" in report["avoidance_reasons"]
    assert "tests_executed_collapse" in report["avoidance_reasons"]
    assert "budget_allow_violation_seen" in report["avoidance_reasons"]
    assert report["metrics"]["exceptional_count"] == 3


def test_analyze_router_telemetry_flags_proof_burn_spike() -> None:
    prior = [
        {
            "timestamp": f"2026-01-01T00:00:0{idx}+00:00",
            "run_intent": "default",
            "router_telemetry": {
                "stage_b_evaluations": 1,
                "escalated": False,
                "stage_a_valid_count": 1,
                "router_status": "selected",
            },
        }
        for idx in range(4)
    ]
    current = [
        {
            "timestamp": f"2026-01-01T00:00:1{idx}+00:00",
            "run_intent": "default",
            "router_telemetry": {
                "stage_b_evaluations": 6,
                "escalated": True,
                "stage_a_valid_count": 0,
                "router_status": "no_admissible_candidate" if idx < 3 else "selected",
            },
        }
        for idx in range(4)
    ]

    report = analyze(
        prior + current,
        Thresholds(
            window_size=4,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
    )

    assert "proof_burn_spike" in report["avoidance_reasons"]
    assert "escalation_cluster" in report["avoidance_reasons"]
    assert "admissible_collapse" in report["avoidance_reasons"]
    assert report["metrics"]["proof_spend_p95"] == 6
    assert report["metrics"]["stage_a_all_fail_rate"] == 1.0


def test_discover_inputs_ignores_latest_pointers(tmp_path: Path) -> None:
    snapshot_a = tmp_path / "20260101T000000Z_sha_deadbeef.json"
    snapshot_b = tmp_path / "20260101T010000Z_sha_beadfeed.json"
    latest = tmp_path / "test_run_provenance.json"
    latest_alias = tmp_path / "latest.json"
    for path in (snapshot_a, snapshot_b, latest, latest_alias):
        path.write_text(json.dumps({"run_intent": "default"}), encoding="utf-8")

    discovered = _discover_inputs(tmp_path, [])

    assert latest not in discovered
    assert latest_alias not in discovered
    assert discovered == sorted([snapshot_a, snapshot_b])


def test_verify_chain_ok_for_synthetic_chain(tmp_path: Path) -> None:
    report = analyze(
        _build_chain(tmp_path, 4),
        Thresholds(
            window_size=2,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
        verify_chain_enabled=True,
    )

    assert report["integrity_checked"] is True
    assert report["integrity_ok"] is True
    assert report["integrity_issues"] == []


def test_verify_chain_detects_mutated_snapshot(tmp_path: Path) -> None:
    runs = _build_chain(tmp_path, 3)
    runs[1]["tests_passed"] = 9

    report = analyze(
        runs,
        Thresholds(
            window_size=2,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
        verify_chain_enabled=True,
    )

    assert report["integrity_ok"] is False
    assert any(issue["issue"] == "hash-mismatch" for issue in report["integrity_issues"])


def test_verify_chain_detects_deleted_middle_snapshot(tmp_path: Path) -> None:
    runs = _build_chain(tmp_path, 4)
    runs = [runs[0], runs[2], runs[3]]

    report = analyze(
        runs,
        Thresholds(
            window_size=2,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
        verify_chain_enabled=True,
    )

    assert report["integrity_ok"] is False
    assert any(issue["issue"] == "prev-mismatch" for issue in report["integrity_issues"])


def test_verify_chain_detects_reordered_files(tmp_path: Path) -> None:
    runs = _build_chain(tmp_path, 3)
    runs[1]["_source"], runs[2]["_source"] = runs[2]["_source"], runs[1]["_source"]

    report = analyze(
        runs,
        Thresholds(
            window_size=2,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
        verify_chain_enabled=True,
    )

    assert report["integrity_ok"] is False
    assert any(issue["issue"] == "prev-mismatch" for issue in report["integrity_issues"])


def test_analyze_reports_deduplicated_source_stats(tmp_path: Path) -> None:
    run = _run(skip_rate=0.05, xfail_rate=0.01, executed=100, passed=95)
    run["provenance_hash"] = "a" * 64
    run["prev_provenance_hash"] = "GENESIS"
    run["hash_algo"] = HASH_ALGO
    run["_source"] = "live"

    report = analyze(
        [run],
        Thresholds(
            window_size=1,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
        source_stats={"live_dir_count": 1, "bundles_count": 2, "index_entries_used": 1},
    )

    assert report["sources"] == {"live_dir_count": 1, "bundles_count": 2, "index_entries_used": 1}
    assert report["deduplicated_runs_total"] == 1


def test_analyzer_cli_reads_bundle_and_archive_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    provenance_dir = tmp_path / "glow" / "test_runs" / "provenance"
    bundles_dir = tmp_path / "glow" / "test_runs" / "bundles"
    provenance_dir.mkdir(parents=True)

    prev = "GENESIS"
    for index in range(3):
        snapshot = provenance_dir / f"run_{index}.json"
        payload = {
            "timestamp": f"2026-01-01T00:00:0{index}+00:00",
            "run_intent": "default",
            "tests_executed": 10,
            "tests_passed": 10,
            "skip_rate": 0.0,
            "xfail_rate": 0.0,
            "hash_algo": HASH_ALGO,
            "prev_provenance_hash": prev,
        }
        payload["provenance_hash"] = compute_provenance_hash(payload, prev)
        prev = str(payload["provenance_hash"])
        snapshot.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")

    assert export_main(["--dir", str(provenance_dir), "--out", str(bundles_dir), "--last", "2"]) == 0

    from scripts.analyze_test_provenance import main as analyze_main

    report_path = tmp_path / "report.json"
    assert analyze_main(["--dir", str(provenance_dir), "--output", str(report_path), "--verify-chain"]) == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["sources"]["bundles_count"] == 1
    assert report["sources"]["index_entries_used"] == 1
    assert report["deduplicated_runs_total"] == 3
