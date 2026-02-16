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


def _write_entry(path: Path, timestamp: str, data: dict[str, object], prev_hash: str) -> str:
    digest = ai._hash_entry(timestamp, data, prev_hash)
    entry = {
        "timestamp": timestamp,
        "data": data,
        "prev_hash": prev_hash,
        "rolling_hash": digest,
    }
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return digest


def _normalize_plan(payload: dict[str, object]) -> dict[str, object]:
    clone = dict(payload)
    clone.pop("generated_at", None)
    return clone


def test_plan_is_deterministic_and_apply_repairs_only_safe(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _repo_env(repo_root)

    logs = tmp_path / "logs"
    logs.mkdir()
    prev = _write_entry(logs / "a.jsonl", "2025-01-01T00:00:00Z", {"a": 1}, "0" * 64)

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

    (logs / "c.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2025-01-01T00:00:02Z",
                "prev_hash": prev,
                "rolling_hash": "0" * 64,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    plan_cmd = [sys.executable, "-m", "scripts.plan_audit_repairs", "logs/"]
    first = subprocess.run(plan_cmd, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    plan_path = tmp_path / "glow" / "audits" / "audit_repair_plan.json"
    plan_one = json.loads(plan_path.read_text(encoding="utf-8"))

    second = subprocess.run(plan_cmd, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stdout + second.stderr
    plan_two = json.loads(plan_path.read_text(encoding="utf-8"))
    assert _normalize_plan(plan_one) == _normalize_plan(plan_two)

    repairs = {repair["paths"][0]: repair for repair in plan_one["repairs"]}
    assert repairs[str(logs / "b.jsonl")]["action"] == "rebuild_chain"
    assert repairs[str(logs / "b.jsonl")]["safe"] is True
    assert repairs[str(logs / "c.jsonl")]["action"] == "manual_required"
    assert repairs[str(logs / "c.jsonl")]["safe"] is False

    verify_before = subprocess.run(
        [sys.executable, "-m", "scripts.verify_audits", "logs/", "--no-input"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert verify_before.returncode == 1
    before_payload = json.loads(
        (tmp_path / "glow" / "audits" / "verify_audits_result.json").read_text(encoding="utf-8")
    )
    before_count = len(before_payload.get("structured_issues", []))

    apply_result = subprocess.run(
        [sys.executable, "-m", "scripts.apply_audit_repairs", "--plan", str(plan_path), "--apply"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert apply_result.returncode == 0, apply_result.stdout + apply_result.stderr

    result_payload = json.loads(
        (tmp_path / "glow" / "audits" / "audit_repair_result.json").read_text(encoding="utf-8")
    )
    assert any(item["path"].endswith("b.jsonl") for item in result_payload["applied"])
    assert any(item.get("reason") == "unsafe_manual_required" for item in result_payload["skipped"])

    verify_after = subprocess.run(
        [sys.executable, "-m", "scripts.verify_audits", "logs/", "--no-input"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert verify_after.returncode == 1
    after_payload = json.loads(
        (tmp_path / "glow" / "audits" / "verify_audits_result.json").read_text(encoding="utf-8")
    )
    after_count = len(after_payload.get("structured_issues", []))
    assert after_count < before_count


def test_apply_requires_explicit_opt_in(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _repo_env(repo_root)

    plan_path = tmp_path / "glow" / "audits" / "audit_repair_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2025-01-01T00:00:00Z",
                "target": "logs/",
                "ok_to_apply": False,
                "issues": [],
                "repairs": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, "-m", "scripts.apply_audit_repairs", "--plan", str(plan_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "Refusing to apply repairs" in proc.stdout
