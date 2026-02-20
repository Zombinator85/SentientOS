from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

import importlib.util
import sys

from typing import Any, Literal

from sentientos.audit_doctor import AuditDoctorReport, diagnose, repair_baseline, repair_runtime, write_docket, write_report
from sentientos.audit_sink import resolve_audit_paths

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("sentientos.audit_reconcile", REPO_ROOT / "sentientos/audit_reconcile.py")
if _spec is None or _spec.loader is None:
    raise RuntimeError("unable to load sentientos.audit_reconcile")
_audit_reconcile = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _audit_reconcile
_spec.loader.exec_module(_audit_reconcile)
AuditReconcileResult = _audit_reconcile.AuditReconcileResult
parse_audit_drift_output = _audit_reconcile.parse_audit_drift_output
reconcile_privileged_audit = _audit_reconcile.reconcile_privileged_audit
result_to_json = _audit_reconcile.result_to_json

FORGE_DIR = REPO_ROOT / "glow/forge"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(REPO_ROOT))


def _write_docket(result: object, verify_output: str, *, doctor_report_path: str | None = None, doctor_docket_path: str | None = None) -> str:
    docket_path = FORGE_DIR / f"audit_docket_{_ts()}.json"
    payload: dict[str, object] = {"kind": "audit_docket", "verify_output": verify_output, **result_to_json(result)}
    if doctor_report_path:
        payload["doctor_report_path"] = doctor_report_path
    if doctor_docket_path:
        payload["doctor_docket_path"] = doctor_docket_path
    return _write_json(docket_path, payload)


def _run_verify() -> tuple[int, str]:
    completed = subprocess.run(["python", "-m", "sentientos.verify_audits", "--strict"], capture_output=True, text=True, cwd=REPO_ROOT, check=False)
    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
    return completed.returncode, output


def _merge_results(primary: object, parsed: object) -> object:
    primary_obj = primary  # type: ignore[assignment]
    parsed_obj = parsed  # type: ignore[assignment]
    findings = list(primary_obj.findings)
    findings.extend(parsed_obj.findings)
    status = primary_obj.status
    if primary_obj.status == "clean" and parsed_obj.status != "clean":
        status = parsed_obj.status
    return AuditReconcileResult(status=status, findings=findings, artifacts_written=list(primary_obj.artifacts_written))


def _accept_drift(reason: str) -> int:
    if os.getenv("SENTIENTOS_AUDIT_ACCEPT_DRIFT") != "1":
        print("SENTIENTOS_AUDIT_ACCEPT_DRIFT=1 is required for --accept-drift")
        return 2
    log_path = resolve_audit_paths(REPO_ROOT).baseline_path
    before = _sha256(log_path) if log_path.exists() else ""
    repair_result = reconcile_privileged_audit(REPO_ROOT, mode="repair")
    after = _sha256(log_path) if log_path.exists() else ""
    note = {
        "kind": "audit_acceptance",
        "reason": reason,
        "before_sha256": before,
        "after_sha256": after,
        **result_to_json(repair_result),
    }
    note_path = FORGE_DIR / f"audit_accept_{_ts()}.json"
    artifact = _write_json(note_path, note)
    print(json.dumps({"mode": "accept", "status": repair_result.status, "artifact": artifact}, sort_keys=True))
    return 0 if repair_result.status in {"clean", "repaired"} else 1


def _doctor_flow() -> tuple[Literal["repaired", "needs_decision", "failed"], str | None, str | None]:
    sink = resolve_audit_paths(REPO_ROOT)
    baseline_status, runtime_status, findings = diagnose(REPO_ROOT, sink.baseline_path, sink.runtime_path)
    actions = repair_runtime(REPO_ROOT, sink.runtime_path)
    baseline_after = baseline_status
    baseline_action = None
    if baseline_status == "drift":
        baseline_after, baseline_action = repair_baseline(REPO_ROOT, sink.baseline_path)
        if baseline_action is not None:
            actions.append(baseline_action)
    samples = [str(item.get("sample", "")) for item in findings.get("runtime_findings", []) if isinstance(item, dict)]
    docket_path = None
    if actions:
        docket_path = write_docket(REPO_ROOT, sink.runtime_path, actions, samples)
    status: Literal["repaired", "needs_decision", "failed"] = "repaired" if actions else "needs_decision" if baseline_after == "needs_decision" else "failed"
    if baseline_after == "ok" and runtime_status == "ok" and not actions:
        status = "repaired"
    report = AuditDoctorReport(
        status=status,
        baseline_status=baseline_after,
        runtime_status=runtime_status,
        actions=actions,
        docket_path=docket_path,
    )
    report_path = write_report(REPO_ROOT, report)
    return report.status, report_path, docket_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile strict audit drift deterministically")
    parser.add_argument("--check", action="store_true", help="verify and fail loudly on drift (default)")
    parser.add_argument("--repair", action="store_true", help="attempt deterministic safe repairs")
    parser.add_argument("--doctor", action="store_true", help="run audit doctor diagnosis + quarantine workflow")
    parser.add_argument("--accept-drift", action="store_true", help="explicitly accept expected drift (requires env flag)")
    parser.add_argument("--reason", default="operator_approved", help="acceptance reason for --accept-drift")
    args = parser.parse_args(argv)

    if args.accept_drift:
        return _accept_drift(str(args.reason))

    verify_rc, verify_output = _run_verify()
    verify_parsed = parse_audit_drift_output(verify_output) if verify_rc != 0 else AuditReconcileResult(status="clean", findings=[], artifacts_written=[])
    reconcile_mode = "repair" if args.repair else "check"

    doctor_status = None
    doctor_report_path = None
    doctor_docket_path = None
    if args.doctor or args.repair:
        doctor_status, doctor_report_path, doctor_docket_path = _doctor_flow()

    reconcile_result = reconcile_privileged_audit(REPO_ROOT, mode=reconcile_mode)
    result = _merge_results(reconcile_result, verify_parsed)

    if args.repair:
        verify_rc, verify_output = _run_verify()
        verify_parsed = parse_audit_drift_output(verify_output) if verify_rc != 0 else AuditReconcileResult(status="clean", findings=[], artifacts_written=[])
        result = _merge_results(reconcile_result, verify_parsed)

    if verify_rc == 0 and result.status in {"clean", "repaired"}:
        print(json.dumps({"mode": reconcile_mode, "status": "clean", "doctor_status": doctor_status, "doctor_report": doctor_report_path, "doctor_docket": doctor_docket_path}, sort_keys=True))
        return 0

    docket = _write_docket(result, verify_output, doctor_report_path=doctor_report_path, doctor_docket_path=doctor_docket_path)
    print(json.dumps({"mode": reconcile_mode, "status": result.status, "docket": docket, "doctor_status": doctor_status, "doctor_report": doctor_report_path, "doctor_docket": doctor_docket_path}, sort_keys=True))
    if args.repair and result.status == "repaired" and verify_rc == 0:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
