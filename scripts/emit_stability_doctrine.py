from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.audit_sink import resolve_audit_paths
from sentientos.vow_artifacts import _resolve_manifest_path

OUTPUT_PATH = Path("glow/contracts/stability_doctrine.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return (False, str(exc))
    out = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    return (completed.returncode == 0, out)


def _latest_audit_docket() -> str | None:
    dockets = sorted(Path("glow/forge").glob("audit_docket_*.json"), key=lambda item: item.name)
    return str(dockets[-1]) if dockets else None


def _strict_audit_status() -> dict[str, Any]:
    ok, output = _run(["python", "-m", "sentientos.verify_audits", "--strict"])
    status = {
        "verify_ok": ok,
        "baseline_status": "unknown",
        "runtime_status": "unknown",
        "baseline_path": "",
        "runtime_path": "",
    }
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "baseline_status" in payload and "runtime_status" in payload:
            status["baseline_status"] = payload["baseline_status"]
            status["runtime_status"] = payload["runtime_status"]
            status["baseline_path"] = payload.get("baseline_path", "")
            status["runtime_path"] = payload.get("runtime_path", "")
    return status


def emit_stability_doctrine(output: Path = OUTPUT_PATH) -> dict[str, Any]:
    audit_module_ok, audit_module_info = _run(["python", "-m", "sentientos.verify_audits", "--help"])
    audit_console_ok, audit_console_info = _run(["python", "scripts/verify_audits_shim.py", "--help"])
    strict = _strict_audit_status()

    manifest_path = _resolve_manifest_path()
    manifest_present = manifest_path.exists()
    manifest_sha = _sha256(manifest_path) if manifest_present else None
    mypy_ok, _ = _run(["make", "mypy-forge"])
    tests_ok, _ = _run(["make", "forge-ci"])

    resolved = resolve_audit_paths(Path.cwd())
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "git_sha": _git_sha(),
        "toolchain": {
            "verify_audits_module": "python -m sentientos.verify_audits --help",
            "verify_audits_console": "python scripts/verify_audits_shim.py --help",
            "audit_tool_module_ok": audit_module_ok,
            "audit_tool_module_info": audit_module_info,
            "audit_tool_console_ok": audit_console_ok,
            "audit_tool_console_info": audit_console_info,
            "verify_audits_available": strict["verify_ok"],
            "verify_audits_info": strict,
        },
        "audit_strict_status": "pass" if strict["verify_ok"] else "fail",
        "audit_drift_detected": strict["baseline_status"] == "drift",
        "baseline_unexpected_change_detected": strict["baseline_status"] == "drift",
        "baseline_integrity_ok": strict["baseline_status"] == "ok",
        "runtime_integrity_ok": strict["runtime_status"] == "ok",
        "audit_baseline_path": str(resolved.baseline_path),
        "audit_runtime_path": str(resolved.runtime_path),
        "last_audit_docket": _latest_audit_docket(),
        "vow_artifacts": {
            "immutable_manifest_path": str(manifest_path),
            "immutable_manifest_present": manifest_present,
            "immutable_manifest_sha256": manifest_sha,
        },
        "mypy_baseline": {"target": "mypy-forge", "passed": mypy_ok},
        "tests_baseline": {"target": "forge-ci", "passed": tests_ok},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    _ = argv
    payload = emit_stability_doctrine()
    print(json.dumps({"tool": "emit_stability_doctrine", "output": str(OUTPUT_PATH), "ok": payload["toolchain"]["verify_audits_available"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
