from __future__ import annotations

import json
from pathlib import Path

from sentientos.auto_remediation import maybe_auto_run_pack, should_auto_run_pack


def _write_pack(root: Path, *, pack_id: str = "pack_1", destructive: bool = False, allowlisted: bool = True) -> dict[str, object]:
    pack_path = root / "glow/forge/remediation/packs" / f"pack_{pack_id}.json"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pack_id": pack_id,
        "incident_id": "inc-1",
        "reason_stack": ["audit_chain_broken"],
        "steps": [
            {
                "name": "repair_audit_index",
                "command": "python scripts/audit_chain_doctor.py --repair-index-only",
                "allowlisted": allowlisted,
                "destructive": destructive,
            }
        ],
    }
    pack_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return {"pack_id": pack_id, "pack_path": str(pack_path.relative_to(root)), "status": "queued", "queued_steps": 1, "incident_id": "inc-1", "reason_stack": ["audit_chain_broken"]}


def test_auto_run_only_in_recovery_mode(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack = _write_pack(tmp_path)
    called: list[str] = []

    def _fake_exec(pack_path: Path, *, root: Path) -> dict[str, object]:
        _ = pack_path, root
        called.append("ran")
        return {"status": "completed", "run_id": "run-1", "report_path": "glow/forge/remediation/runs/run-1.json"}

    monkeypatch.setattr("sentientos.auto_remediation.run_remediation_pack.execute_pack_file", _fake_exec)

    result = maybe_auto_run_pack(tmp_path, operating_mode="normal", context="forge_run", pack=pack, governance_trace_id="trace-1", incident_id="inc-1")
    assert result.attempted is False
    assert result.status == "idle"
    assert called == []


def test_cooldown_prevents_repeated_runs(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack = _write_pack(tmp_path)
    (tmp_path / "pulse").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pulse/auto_remediation_attempts.jsonl").write_text(
        json.dumps({"attempted_at": "2099-01-01T00:00:00Z", "pack_id": "pack_1", "incident_id": "inc-1", "status": "failed"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SENTIENTOS_AUTO_REMEDIATION_COOLDOWN_MINUTES", "999999")

    decision = should_auto_run_pack(tmp_path, operating_mode="recovery", pack=pack, incident_id="inc-1", governance_trace_id="trace-1")
    assert decision.status == "cooldown"


def test_successful_run_prevents_further_attempts(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    (tmp_path / "glow/forge/remediation/runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/remediation/runs/run_20990101_pack_1.json").write_text(
        json.dumps({"run_id": "run_20990101_pack_1", "pack_id": "pack_1", "status": "completed"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    decision = should_auto_run_pack(tmp_path, operating_mode="recovery", pack=pack, incident_id="inc-1", governance_trace_id="trace-1")
    assert decision.status == "succeeded"


def test_failed_run_attempts_respect_max_attempts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack = _write_pack(tmp_path)
    monkeypatch.setenv("SENTIENTOS_AUTO_REMEDIATION_MAX_ATTEMPTS", "2")
    (tmp_path / "pulse").mkdir(parents=True, exist_ok=True)
    attempts = tmp_path / "pulse/auto_remediation_attempts.jsonl"
    attempts.write_text(
        "\n".join(
            [
                json.dumps({"attempted_at": "2026-01-01T00:00:00Z", "pack_id": "pack_1", "incident_id": "inc-1", "status": "failed"}, sort_keys=True),
                json.dumps({"attempted_at": "2026-01-01T01:00:00Z", "pack_id": "pack_1", "incident_id": "inc-1", "status": "failed"}, sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    decision = should_auto_run_pack(tmp_path, operating_mode="recovery", pack=pack, incident_id="inc-1", governance_trace_id="trace-1")
    assert decision.status == "failed"
    assert decision.reason == "max_attempts_reached"


def test_failed_auto_run_records_attempt(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack = _write_pack(tmp_path)

    def _fake_exec(pack_path: Path, *, root: Path) -> dict[str, object]:
        _ = pack_path, root
        return {"status": "failed", "run_id": "run-failed", "report_path": "glow/forge/remediation/runs/run-failed.json"}

    monkeypatch.setattr("sentientos.auto_remediation.run_remediation_pack.execute_pack_file", _fake_exec)
    result = maybe_auto_run_pack(tmp_path, operating_mode="recovery", context="forge_run", pack=pack, governance_trace_id="trace-1", incident_id="inc-1")
    assert result.attempted is True
    assert result.status == "failed"
    rows = [json.loads(line) for line in (tmp_path / "pulse/auto_remediation_attempts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["run_id"] == "run-failed"
