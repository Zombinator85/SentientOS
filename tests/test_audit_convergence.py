from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import audit_immutability as ai


def _repo_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["LUMOS_AUTO_APPROVE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _write_valid_entry(path: Path, timestamp: str, data: dict[str, object], prev_hash: str) -> str:
    digest = ai._hash_entry(timestamp, data, prev_hash)
    payload = {
        "timestamp": timestamp,
        "data": data,
        "prev_hash": prev_hash,
        "rolling_hash": digest,
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return digest


def _build_broken_logs(logs: Path) -> None:
    _write_valid_entry(logs / "a.jsonl", "2025-01-01T00:00:00Z", {"a": 1}, "0" * 64)

    broken_hash = ai._hash_entry("2025-01-01T00:00:01Z", {"b": 2}, "bad-prev")
    (logs / "b.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2025-01-01T00:00:01Z",
                "data": {"b": 2},
                "prev_hash": "bad-prev",
                "rolling_hash": broken_hash,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    c_first_prev = "independent-prev"
    c_first_hash = ai._hash_entry("2025-01-01T00:00:03Z", {"c": 3}, c_first_prev)
    c_second_hash = ai._hash_entry("2025-01-01T00:00:02Z", {"c": 4}, c_first_hash)
    (logs / "c.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2025-01-01T00:00:03Z",
                        "data": {"c": 3},
                        "prev_hash": c_first_prev,
                        "rolling_hash": c_first_hash,
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2025-01-01T00:00:02Z",
                        "data": {"c": 4},
                        "prev_hash": c_first_hash,
                        "rolling_hash": c_second_hash,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_converge_audits_is_deterministic_and_reports_manual_issues(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _repo_env(repo_root)

    logs = tmp_path / "logs"
    logs.mkdir()
    _build_broken_logs(logs)

    cmd = [sys.executable, "-m", "scripts.converge_audits", "logs/", "--max-iterations", "5"]
    run = subprocess.run(cmd, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr

    report_path = tmp_path / "glow" / "audits" / "audit_convergence_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["counts_before"]["issues_total"] > report["counts_after"]["issues_total"]
    assert report["applied_repairs"] >= 1
    assert report["ok"] is False
    assert report["no_safe_repairs_remaining"] is True
    assert report["remaining_manual_issues"], "manual-required issues should be surfaced"

    iteration_names = [item["iteration"] for item in report["iterations"]]
    assert iteration_names == [f"iter_{index:02d}" for index in range(1, len(iteration_names) + 1)]
    assert len(iteration_names) <= 5


def test_converge_writes_quarantine_index_records(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _repo_env(repo_root)

    logs = tmp_path / "logs"
    logs.mkdir()
    _build_broken_logs(logs)

    run = subprocess.run(
        [sys.executable, "-m", "scripts.converge_audits", "logs/", "--max-iterations", "3"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr

    index_path = tmp_path / "glow" / "audits" / "quarantine_index.jsonl"
    lines = [line for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "quarantine index should include manual-required entries"

    first = json.loads(lines[0])
    assert first["original_path"].endswith("c.jsonl")
    assert first["quarantine_path"]
    assert "timestamp_order_violation" in first["reason_codes"]
    assert first["hash_before"] == first["hash_after"]
    assert first["repair_id"]


def test_converge_no_apply_mode_is_plan_only(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _repo_env(repo_root)

    logs = tmp_path / "logs"
    logs.mkdir()
    _build_broken_logs(logs)

    run = subprocess.run(
        [sys.executable, "-m", "scripts.converge_audits", "logs/", "--max-iterations", "4", "--no-apply"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr

    report = json.loads((tmp_path / "glow" / "audits" / "audit_convergence_report.json").read_text(encoding="utf-8"))
    assert report["applied_repairs"] == 0
    assert len(report["iterations"]) == 1
    assert report["iterations"][0]["stopped_reason"] == "no_apply_mode"
