from __future__ import annotations

import json
from pathlib import Path

from scripts.forensic_run_report import build_forensic_report
from scripts.provenance_hash_chain import HASH_ALGO, compute_provenance_hash


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_provenance_chain(test_run_dir: Path) -> None:
    provenance_dir = test_run_dir / "provenance"
    run_a = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "run_intent": "default",
        "execution_mode": "full",
        "tests_executed": 10,
        "hash_algo": HASH_ALGO,
        "prev_provenance_hash": None,
    }
    run_a["provenance_hash"] = compute_provenance_hash(run_a, None)

    run_b = {
        "timestamp": "2026-01-01T00:00:01+00:00",
        "run_intent": "default",
        "execution_mode": "full",
        "tests_executed": 11,
        "hash_algo": HASH_ALGO,
        "prev_provenance_hash": run_a["provenance_hash"],
    }
    run_b["provenance_hash"] = compute_provenance_hash(run_b, str(run_a["provenance_hash"]))

    _write_json(provenance_dir / "20260101T000000Z_sha_a.json", run_a)
    _write_json(provenance_dir / "20260101T000001Z_sha_b.json", run_b)
    _write_json(test_run_dir / "test_run_provenance.json", run_b)


def _write_pressure_state(routing_dir: Path) -> None:
    payload = {
        "state": {"consecutive_no_admissible": 0, "recent_runs": []},
        "hash_algo": HASH_ALGO,
        "prev_state_hash": "GENESIS",
        "governor_version": "v1",
        "created_at": "2026-01-01T00:00:02+00:00",
    }
    import hashlib

    digest = hashlib.sha256()
    digest.update(b"GENESIS")
    digest.update(b"\n")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest.update(canonical)
    payload["state_hash"] = digest.hexdigest()

    _write_json(routing_dir / "pressure_state" / "snapshots" / "20260101T000002Z_aaa.json", payload)
    _write_json(routing_dir / "pressure_state" / "latest.json", payload)


def _write_amendment_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "timestamp": "2026-01-01T00:00:03+00:00",
            "proposal_id": "p1",
            "metadata": {
                "event_type": "proof_budget",
                "router_telemetry": {"stage_b_evaluations": 2, "escalated": False, "router_status": "selected"},
            },
        },
        {
            "timestamp": "2026-01-01T00:00:04+00:00",
            "proposal_id": "p2",
            "metadata": {
                "event_type": "proof_budget_governor",
                "pipeline": "GenesisForge",
                "capability": "demo",
                "router_attempt": 1,
                "governor": {
                    "mode": "normal",
                    "pressure_state_new_hash": "abc",
                    "state_update_skipped": False,
                },
            },
        },
    ]
    path.write_text("\n".join(json.dumps(item, sort_keys=True) for item in lines) + "\n", encoding="utf-8")


def test_forensic_report_deterministic_for_same_inputs(tmp_path: Path) -> None:
    test_run_dir = tmp_path / "glow" / "test_runs"
    routing_dir = tmp_path / "glow" / "routing"
    amendment_log = tmp_path / "integration" / "amendment_log.jsonl"

    _write_provenance_chain(test_run_dir)
    _write_pressure_state(routing_dir)
    _write_amendment_log(amendment_log)
    _write_json(test_run_dir / "test_trend_report.json", {"avoidance_reasons": ["proof_burn_spike"]})
    _write_json(test_run_dir / "router_telemetry_report.json", {"avoidance_reasons": ["proof_burn_spike"]})

    first = build_forensic_report(
        repo_root=tmp_path,
        test_run_dir=test_run_dir,
        routing_dir=routing_dir,
        amendment_log_path=amendment_log,
    )
    second = build_forensic_report(
        repo_root=tmp_path,
        test_run_dir=test_run_dir,
        routing_dir=routing_dir,
        amendment_log_path=amendment_log,
    )

    assert first["routing"] == second["routing"]
    assert first["governor"] == second["governor"]
    assert first["test"]["integrity_ok"] is True


def test_forensic_report_handles_missing_artifacts(tmp_path: Path) -> None:
    report = build_forensic_report(
        repo_root=tmp_path,
        test_run_dir=tmp_path / "glow" / "test_runs",
        routing_dir=tmp_path / "glow" / "routing",
        amendment_log_path=tmp_path / "integration" / "amendment_log.jsonl",
    )

    assert report["test"]["provenance_path"] is None
    assert report["test"]["failure_digest_path"] is None
    assert report["artifacts"]["bundle_paths"] == []
    assert report["governor"]["pressure_state"]["latest_path"] is None


def test_forensic_report_integrity_summary_reflects_failures(tmp_path: Path) -> None:
    test_run_dir = tmp_path / "glow" / "test_runs"
    routing_dir = tmp_path / "glow" / "routing"
    amendment_log = tmp_path / "integration" / "amendment_log.jsonl"

    _write_provenance_chain(test_run_dir)
    # break the hash chain
    broken = json.loads((test_run_dir / "provenance" / "20260101T000001Z_sha_b.json").read_text(encoding="utf-8"))
    broken["tests_executed"] = 999
    _write_json(test_run_dir / "provenance" / "20260101T000001Z_sha_b.json", broken)
    _write_json(test_run_dir / "test_run_provenance.json", broken)

    _write_pressure_state(routing_dir)
    # invalidate pressure latest pointer
    _write_json(routing_dir / "pressure_state" / "latest.json", {"state_hash": "not-in-snapshot"})
    _write_amendment_log(amendment_log)

    report = build_forensic_report(
        repo_root=tmp_path,
        test_run_dir=test_run_dir,
        routing_dir=routing_dir,
        amendment_log_path=amendment_log,
    )

    assert report["test"]["integrity_checked"] is True
    assert report["test"]["integrity_ok"] is False
    assert report["governor"]["pressure_state"]["chain_integrity_checked"] is True
    assert report["governor"]["pressure_state"]["chain_integrity_ok"] is False
