from __future__ import annotations

import json
from pathlib import Path

import audit_immutability as ai
from scripts.capture_audit_baseline import capture_baseline
from scripts.detect_audit_drift import detect_drift


def _make_clean_logs(target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    log = target / "audit.jsonl"
    ai.append_entry(log, {"event": "alpha"})
    ai.append_entry(log, {"event": "beta"})
    return log


def test_capture_audit_baseline_is_deterministic(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    _make_clean_logs(logs)

    first = capture_baseline(target=logs, output=tmp_path / "baseline_1.json", accept_manual=False)
    second = capture_baseline(target=logs, output=tmp_path / "baseline_2.json", accept_manual=False)

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["manifest"] == second["manifest"]
    assert first["baseline_fingerprint"] == second["baseline_fingerprint"]


def test_detect_audit_drift_reports_new_and_resolved_issues(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    log = _make_clean_logs(logs)

    clean_baseline_path = tmp_path / "baseline_clean.json"
    capture_baseline(target=logs, output=clean_baseline_path, accept_manual=False)

    with log.open("a", encoding="utf-8") as handle:
        handle.write('{"oops":')

    dirty_report = detect_drift(
        target=logs,
        baseline_path=clean_baseline_path,
        output_path=tmp_path / "drift_dirty.json",
    )
    assert dirty_report["drifted"] is True
    assert dirty_report["new_issues"]

    accepted_baseline_path = tmp_path / "baseline_accepted.json"
    accepted_baseline = capture_baseline(target=logs, output=accepted_baseline_path, accept_manual=True)
    assert accepted_baseline["manual_issues_accepted"] is True

    lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    log.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    resolved_report = detect_drift(
        target=logs,
        baseline_path=accepted_baseline_path,
        output_path=tmp_path / "drift_resolved.json",
    )
    assert resolved_report["drifted"] is True
    assert resolved_report["resolved_issues"]


def test_capture_accept_manual_records_explicit_status(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    log = _make_clean_logs(logs)
    with log.open("a", encoding="utf-8") as handle:
        handle.write('{"oops":')

    payload = capture_baseline(target=logs, output=tmp_path / "baseline.json", accept_manual=True)
    on_disk = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))

    assert payload["ok"] is False
    assert payload["manual_issues_accepted"] is True
    assert on_disk["manual_issues_accepted"] is True
