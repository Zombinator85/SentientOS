from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.ci_baseline import evaluate_ci_baseline_drift
from sentientos.forge_index import rebuild_index

DEFAULT_OUTPUT = Path("glow/contracts/contract_status.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _git_sha() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _drift_explanation(report: dict[str, Any]) -> str | None:
    explanation = report.get("drift_explanation")
    if isinstance(explanation, str):
        return explanation
    fallback = report.get("explanation")
    return fallback if isinstance(fallback, str) else None


def _baseline_meta(baseline: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    if not baseline:
        return (None, None, None)

    captured_by = baseline.get("captured_by")
    captured_at = baseline.get("captured_at")
    tool_version = baseline.get("tool_version")

    provenance = baseline.get("provenance")
    if isinstance(provenance, dict):
        captured_by = captured_by or provenance.get("captured_by")
        captured_at = captured_at or provenance.get("captured_at")
        tool_version = tool_version or provenance.get("tool_version")

    return (
        str(captured_by) if isinstance(captured_by, str) else None,
        str(captured_at) if isinstance(captured_at, str) else None,
        str(tool_version) if isinstance(tool_version, str) else None,
    )




def _resolve_vow_manifest_path() -> Path:
    if Path("/vow").exists():
        return Path("/vow/immutable_manifest.json")
    return Path("vow/immutable_manifest.json")


def _vow_manifest_meta(manifest: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    if not manifest:
        return (None, None, None)

    manifest_sha = manifest.get("manifest_sha256")
    captured_by = manifest.get("captured_by")
    tool_version = manifest.get("tool_version")

    return (
        str(manifest_sha) if isinstance(manifest_sha, str) else None,
        str(captured_by) if isinstance(captured_by, str) else None,
        str(tool_version) if isinstance(tool_version, str) else None,
    )

def _domain_status(
    *,
    domain_name: str,
    baseline_path: Path,
    drift_report_path: Path | None,
    strict_gate_envvar: str,
    git_sha: str,
    baseline_optional: bool = False,
) -> dict[str, Any]:
    baseline_present = baseline_path.exists()
    baseline_payload = _read_json(baseline_path) if baseline_present else None
    drift_payload = _read_json(drift_report_path) if drift_report_path and drift_report_path.exists() else None

    captured_by, captured_at, tool_version = _baseline_meta(baseline_payload)

    if not baseline_present and not baseline_optional:
        drifted: bool | None = None
        drift_type = "baseline_missing"
        drift_explanation = None
    else:
        drifted = bool(drift_payload.get("drifted", False)) if isinstance(drift_payload, dict) else False
        raw_drift_type = drift_payload.get("drift_type") if isinstance(drift_payload, dict) else None
        drift_type = raw_drift_type if isinstance(raw_drift_type, str) and raw_drift_type else "none"
        drift_explanation = _drift_explanation(drift_payload) if isinstance(drift_payload, dict) else None

    payload: dict[str, Any] = {
        "domain_name": domain_name,
        "baseline_present": baseline_present,
        "last_baseline_path": str(baseline_path) if baseline_present else None,
        "drift_report_path": str(drift_report_path) if drift_report_path and drift_report_path.exists() else None,
        "drifted": drifted,
        "drift_type": drift_type,
        "drift_explanation": drift_explanation,
        "drift_provenance": drift_payload.get("provenance") if isinstance(drift_payload, dict) else None,
        "fingerprint_changed": (
            drift_payload.get("fingerprint_changed")
            if isinstance(drift_payload, dict) and "fingerprint_changed" in drift_payload
            else None
        ),
        "tuple_diff_detected": (
            drift_payload.get("tuple_diff_detected")
            if isinstance(drift_payload, dict) and "tuple_diff_detected" in drift_payload
            else None
        ),
        "strict_gate_envvar": strict_gate_envvar,
        "captured_by": captured_by,
        "captured_at": captured_at,
        "tool_version": tool_version,
        "git_sha": git_sha,
    }
    return payload


def emit_contract_status(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    git_sha = _git_sha()
    contracts = [
        _domain_status(
            domain_name="audits",
            baseline_path=Path("glow/audits/baseline/audit_baseline.json"),
            drift_report_path=Path("glow/audits/audit_drift_report.json"),
            strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_AUDIT_DRIFT",
            git_sha=git_sha,
        ),
        _domain_status(
            domain_name="pulse",
            baseline_path=Path("glow/pulse/baseline/pulse_schema_baseline.json"),
            drift_report_path=Path("glow/pulse/pulse_schema_drift_report.json"),
            strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_PULSE_DRIFT",
            git_sha=git_sha,
        ),
        _domain_status(
            domain_name="perception",
            baseline_path=Path("glow/perception/baseline/perception_schema_baseline.json"),
            drift_report_path=Path("glow/perception/perception_schema_drift_report.json"),
            strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_PERCEPTION_SCHEMA_DRIFT",
            git_sha=git_sha,
        ),
        _domain_status(
            domain_name="self_model",
            baseline_path=Path("glow/self/baseline/self_model_baseline.json"),
            drift_report_path=Path("glow/self/self_model_drift_report.json"),
            strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_SELF_MODEL_DRIFT",
            git_sha=git_sha,
        ),
        _domain_status(
            domain_name="federation_identity",
            baseline_path=Path("glow/federation/baseline/federation_identity_baseline.json"),
            drift_report_path=Path("glow/federation/federation_identity_drift_report.json"),
            strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_FEDERATION_IDENTITY_DRIFT",
            git_sha=git_sha,
        ),
        _domain_status(
            domain_name="vow_manifest",
            baseline_path=_resolve_vow_manifest_path(),
            drift_report_path=Path("glow/audits/audit_immutability_result.json"),
            strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_VOW_MANIFEST_DRIFT",
            git_sha=git_sha,
            baseline_optional=True,
        ),
        _ci_baseline_status(git_sha=git_sha),
        _stability_doctrine_status(git_sha=git_sha),
        _forge_observatory_status(git_sha=git_sha),
    ]

    vow_manifest = next((entry for entry in contracts if entry.get("domain_name") == "vow_manifest"), None)
    if isinstance(vow_manifest, dict):
        manifest_path = _resolve_vow_manifest_path()
        manifest_present = manifest_path.exists()
        manifest_payload = _read_json(manifest_path) if manifest_present else None
        manifest_sha, manifest_captured_by, manifest_tool_version = _vow_manifest_meta(manifest_payload)
        if not manifest_present:
            vow_manifest["baseline_present"] = False
            vow_manifest["last_baseline_path"] = None
            vow_manifest["drifted"] = None
            vow_manifest["drift_type"] = "preflight_required"
            vow_manifest["drift_explanation"] = "vow immutable manifest missing; run make vow-manifest"
        vow_manifest["manifest_sha256"] = manifest_sha
        vow_manifest["manifest_captured_by"] = manifest_captured_by
        vow_manifest["manifest_tool_version"] = manifest_tool_version

    payload = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "git_sha": git_sha,
        "contracts": contracts,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _ci_baseline_status(*, git_sha: str) -> dict[str, Any]:
    baseline_path = Path("glow/contracts/ci_baseline.json")
    baseline_present = baseline_path.exists()
    baseline_payload = _read_json(baseline_path) if baseline_present else None
    drift = evaluate_ci_baseline_drift(baseline_payload)
    failed_count = baseline_payload.get("failed_count") if isinstance(baseline_payload, dict) else None
    passed = baseline_payload.get("passed") if isinstance(baseline_payload, dict) else None
    top_clusters = baseline_payload.get("top_clusters") if isinstance(baseline_payload, dict) else None

    return {
        "domain_name": "ci_baseline",
        "baseline_present": baseline_present,
        "last_baseline_path": str(baseline_path) if baseline_present else None,
        "drift_report_path": None,
        "drifted": drift.drifted,
        "drift_type": drift.drift_type,
        "drift_explanation": drift.drift_explanation,
        "drift_provenance": None,
        "fingerprint_changed": None,
        "tuple_diff_detected": None,
        "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_CI_BASELINE_DRIFT",
        "captured_by": None,
        "captured_at": baseline_payload.get("generated_at") if isinstance(baseline_payload, dict) else None,
        "tool_version": None,
        "git_sha": git_sha,
        "runner": baseline_payload.get("runner") if isinstance(baseline_payload, dict) else "scripts.run_tests",
        "passed": passed,
        "failed_count": failed_count,
        "top_clusters": top_clusters if isinstance(top_clusters, list) else [],
    }



def _stability_doctrine_status(*, git_sha: str) -> dict[str, Any]:
    doctrine_path = Path("glow/contracts/stability_doctrine.json")
    payload = _read_json(doctrine_path) if doctrine_path.exists() else None
    toolchain = payload.get("toolchain") if isinstance(payload, dict) and isinstance(payload.get("toolchain"), dict) else {}
    vow = payload.get("vow_artifacts") if isinstance(payload, dict) and isinstance(payload.get("vow_artifacts"), dict) else {}
    verify_ok = bool(toolchain.get("verify_audits_available", False))
    manifest_ok = bool(vow.get("immutable_manifest_present", False))
    drifted = not (verify_ok and manifest_ok)
    reason_bits: list[str] = []
    if not verify_ok:
        reason_bits.append("toolchain_missing")
    if not manifest_ok:
        reason_bits.append("vow_artifacts_missing")

    return {
        "domain_name": "stability_doctrine",
        "baseline_present": doctrine_path.exists(),
        "last_baseline_path": str(doctrine_path) if doctrine_path.exists() else None,
        "drift_report_path": None,
        "drifted": drifted if doctrine_path.exists() else None,
        "drift_type": "none" if doctrine_path.exists() and not drifted else ("stability_not_ready" if doctrine_path.exists() else "baseline_missing"),
        "drift_explanation": ",".join(reason_bits) if reason_bits else None,
        "drift_provenance": None,
        "fingerprint_changed": None,
        "tuple_diff_detected": None,
        "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_STABILITY_DOCTRINE",
        "captured_by": payload.get("git_sha") if isinstance(payload, dict) else None,
        "captured_at": payload.get("generated_at") if isinstance(payload, dict) else None,
        "tool_version": None,
        "git_sha": git_sha,
        "verify_audits_available": verify_ok,
        "immutable_manifest_present": manifest_ok,
        "immutable_manifest_sha256": vow.get("immutable_manifest_sha256") if isinstance(vow.get("immutable_manifest_sha256"), str) else None,
    }

def _forge_observatory_status(*, git_sha: str) -> dict[str, Any]:
    index_path = Path("glow/forge/index.json")
    receipts_path = Path("pulse/forge_receipts.jsonl")

    try:
        index_payload = rebuild_index(Path.cwd())
        index_present = True
    except Exception:
        index_payload = None
        index_present = False

    receipts_readable = receipts_path.exists()
    last_report_parseable = False
    corrupt_count = 0
    if isinstance(index_payload, dict):
        corrupt = index_payload.get("corrupt_count")
        if isinstance(corrupt, dict):
            total = corrupt.get("total")
            if isinstance(total, int):
                corrupt_count = total
        latest_reports = index_payload.get("latest_reports")
        if isinstance(latest_reports, list) and latest_reports:
            last_report_parseable = isinstance(latest_reports[-1], dict)

    return {
        "domain_name": "forge_observatory",
        "baseline_present": index_present,
        "last_baseline_path": str(index_path) if index_present else None,
        "drift_report_path": None,
        "drifted": bool(corrupt_count),
        "drift_type": "corrupt_jsonl" if corrupt_count else "none",
        "drift_explanation": f"corrupt_jsonl_lines={corrupt_count}",
        "drift_provenance": None,
        "fingerprint_changed": None,
        "tuple_diff_detected": None,
        "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_FORGE_OBSERVATORY_DRIFT",
        "captured_by": None,
        "captured_at": index_payload.get("generated_at") if isinstance(index_payload, dict) else None,
        "tool_version": None,
        "git_sha": git_sha,
        "index_present": index_present,
        "receipts_readable": receipts_readable,
        "last_report_parseable": last_report_parseable,
        "corrupt_jsonl_lines": corrupt_count,
    }


def main(argv: list[str] | None = None) -> int:
    _ = argv
    payload = emit_contract_status(DEFAULT_OUTPUT)
    print(json.dumps({"tool": "emit_contract_status", "output": str(DEFAULT_OUTPUT), "domains": len(payload.get("contracts", []))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
