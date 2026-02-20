from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sentientos import audit_doctor


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def test_repair_runtime_quarantines_and_keeps_valid(tmp_path: Path) -> None:
    runtime = tmp_path / "pulse" / "audit" / "privileged_audit.runtime.jsonl"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    valid = '{"timestamp":"2026-01-01T00:00:00Z","prev_hash":"%s","rolling_hash":"a","data":{"ok":1}}' % ("0" * 64)
    malformed = '{"timestamp":"2026-01-02T00:00:00Z","data":'
    truncated = '{"timestamp":"2026-01-03T00:00:00Z"'
    runtime.write_text(valid + "\n" + malformed + "\n" + truncated, encoding="utf-8")

    before = _sha(runtime)
    actions = audit_doctor.repair_runtime(tmp_path, runtime)
    after = _sha(runtime)

    assert actions
    assert before != after
    text = runtime.read_text(encoding="utf-8")
    assert valid in text
    assert malformed not in text
    assert truncated not in text

    quarantine = sorted((runtime.parent / "quarantine").glob("*.jsonl"))
    assert len(quarantine) == 2
    qtext = "\n".join(item.read_text(encoding="utf-8") for item in quarantine)
    assert malformed in qtext
    assert truncated in qtext


def test_repair_baseline_restores_to_head(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "logs").mkdir(parents=True)
    baseline = repo / "logs" / "privileged_audit.jsonl"
    baseline.write_text('{"timestamp":"2026-01-01T00:00:00Z","data":{}}\n', encoding="utf-8")

    import subprocess

    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Audit Bot"], cwd=repo, check=True)
    subprocess.run(["git", "add", "logs/privileged_audit.jsonl"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, check=True)

    baseline.write_text(baseline.read_text(encoding="utf-8") + '{"timestamp":"2026-01-02T00:00:00Z","data":{}}\n', encoding="utf-8")
    status, action = audit_doctor.repair_baseline(repo, baseline)
    assert status == "repaired"
    assert action is not None

    head = subprocess.run(["git", "show", "HEAD:logs/privileged_audit.jsonl"], cwd=repo, check=True, capture_output=True, text=True).stdout
    assert baseline.read_text(encoding="utf-8") == head


def test_write_docket_and_report(tmp_path: Path) -> None:
    runtime = tmp_path / "pulse/audit/privileged_audit.runtime.jsonl"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("", encoding="utf-8")
    action = audit_doctor.RuntimeRepairAction(
        kind="quarantine_malformed",
        source_path=str(runtime),
        dest_path=str(tmp_path / "pulse/audit/quarantine/x.jsonl"),
        line_count=1,
        sha_before="a",
        sha_after="b",
        notes="test",
    )
    docket = audit_doctor.write_docket(tmp_path, runtime, [action], ["bad line"])
    report = audit_doctor.write_report(
        tmp_path,
        audit_doctor.AuditDoctorReport(
            status="repaired",
            baseline_status="ok",
            runtime_status="broken",
            actions=[action],
            docket_path=docket,
        ),
    )
    docket_payload = json.loads((tmp_path / docket).read_text(encoding="utf-8"))
    report_payload = json.loads((tmp_path / report).read_text(encoding="utf-8"))
    assert docket_payload["quarantine_paths"]
    assert report_payload["status"] == "repaired"
