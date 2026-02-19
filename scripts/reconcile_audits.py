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


def _write_docket(result: AuditReconcileResult, verify_output: str) -> str:
    docket_path = FORGE_DIR / f"audit_docket_{_ts()}.json"
    return _write_json(docket_path, {"kind": "audit_docket", "verify_output": verify_output, **result_to_json(result)})


def _run_verify() -> tuple[int, str]:
    completed = subprocess.run(["python", "-m", "sentientos.verify_audits", "--strict"], capture_output=True, text=True, cwd=REPO_ROOT, check=False)
    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
    return completed.returncode, output


def _merge_results(primary: AuditReconcileResult, parsed: AuditReconcileResult) -> AuditReconcileResult:
    findings = list(primary.findings)
    findings.extend(parsed.findings)
    status = primary.status
    if primary.status == "clean" and parsed.status != "clean":
        status = parsed.status
    return AuditReconcileResult(status=status, findings=findings, artifacts_written=list(primary.artifacts_written))


def _accept_drift(reason: str) -> int:
    if os.getenv("SENTIENTOS_AUDIT_ACCEPT_DRIFT") != "1":
        print("SENTIENTOS_AUDIT_ACCEPT_DRIFT=1 is required for --accept-drift")
        return 2
    log_path = REPO_ROOT / "logs/privileged_audit.jsonl"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile strict audit drift deterministically")
    parser.add_argument("--check", action="store_true", help="verify and fail loudly on drift (default)")
    parser.add_argument("--repair", action="store_true", help="attempt deterministic safe repairs")
    parser.add_argument("--accept-drift", action="store_true", help="explicitly accept expected drift (requires env flag)")
    parser.add_argument("--reason", default="operator_approved", help="acceptance reason for --accept-drift")
    args = parser.parse_args(argv)

    if args.accept_drift:
        return _accept_drift(str(args.reason))

    verify_rc, verify_output = _run_verify()
    verify_parsed = parse_audit_drift_output(verify_output)
    reconcile_mode = "repair" if args.repair else "check"
    reconcile_result = reconcile_privileged_audit(REPO_ROOT, mode=reconcile_mode)
    result = _merge_results(reconcile_result, verify_parsed)

    if verify_rc == 0 and result.status == "clean":
        print(json.dumps({"mode": reconcile_mode, "status": "clean"}, sort_keys=True))
        return 0

    docket = _write_docket(result, verify_output)
    print(json.dumps({"mode": reconcile_mode, "status": result.status, "docket": docket}, sort_keys=True))
    if args.repair and result.status == "repaired":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
