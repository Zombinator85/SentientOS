from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.detect_audit_drift import detect_drift as detect_audit_drift
from scripts.detect_federation_identity_drift import detect_drift as detect_federation_identity_drift
from scripts.detect_pulse_schema_drift import detect_drift as detect_pulse_schema_drift
from scripts.detect_perception_schema_drift import detect_drift as detect_perception_schema_drift
from scripts.detect_self_model_drift import detect_drift as detect_self_model_drift


@dataclass(frozen=True)
class DriftDomain:
    name: str
    baseline_path: Path
    report_path: Path
    strict_gate_envvar: str
    detector: Callable[[], dict[str, Any]]


def _audit_detector() -> dict[str, Any]:
    return detect_audit_drift(
        target=Path("logs"),
        baseline_path=Path("glow/audits/baseline/audit_baseline.json"),
        output_path=Path("glow/audits/audit_drift_report.json"),
        max_iterations=1,
    )


def _pulse_detector() -> dict[str, Any]:
    return detect_pulse_schema_drift(
        baseline_path=Path("glow/pulse/baseline/pulse_schema_baseline.json"),
        output_path=Path("glow/pulse/pulse_schema_drift_report.json"),
    )


def _perception_detector() -> dict[str, Any]:
    return detect_perception_schema_drift(
        baseline_path=Path("glow/perception/baseline/perception_schema_baseline.json"),
        output_path=Path("glow/perception/perception_schema_drift_report.json"),
    )


def _self_detector() -> dict[str, Any]:
    return detect_self_model_drift(
        baseline_path=Path("glow/self/baseline/self_model_baseline.json"),
        output_path=Path("glow/self/self_model_drift_report.json"),
    )


def _federation_detector() -> dict[str, Any]:
    return detect_federation_identity_drift(
        baseline_path=Path("glow/federation/baseline/federation_identity_baseline.json"),
        output_path=Path("glow/federation/federation_identity_drift_report.json"),
    )


DRIFT_DOMAINS: tuple[DriftDomain, ...] = (
    DriftDomain(
        name="audits",
        baseline_path=Path("glow/audits/baseline/audit_baseline.json"),
        report_path=Path("glow/audits/audit_drift_report.json"),
        strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_AUDIT_DRIFT",
        detector=_audit_detector,
    ),
    DriftDomain(
        name="pulse",
        baseline_path=Path("glow/pulse/baseline/pulse_schema_baseline.json"),
        report_path=Path("glow/pulse/pulse_schema_drift_report.json"),
        strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_PULSE_DRIFT",
        detector=_pulse_detector,
    ),
    DriftDomain(
        name="perception",
        baseline_path=Path("glow/perception/baseline/perception_schema_baseline.json"),
        report_path=Path("glow/perception/perception_schema_drift_report.json"),
        strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_PERCEPTION_SCHEMA_DRIFT",
        detector=_perception_detector,
    ),
    DriftDomain(
        name="self_model",
        baseline_path=Path("glow/self/baseline/self_model_baseline.json"),
        report_path=Path("glow/self/self_model_drift_report.json"),
        strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_SELF_MODEL_DRIFT",
        detector=_self_detector,
    ),
    DriftDomain(
        name="federation_identity",
        baseline_path=Path("glow/federation/baseline/federation_identity_baseline.json"),
        report_path=Path("glow/federation/federation_identity_drift_report.json"),
        strict_gate_envvar="SENTIENTOS_CI_FAIL_ON_FEDERATION_IDENTITY_DRIFT",
        detector=_federation_detector,
    ),
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _drift_explanation(payload: dict[str, Any]) -> str:
    explanation = payload.get("drift_explanation")
    if isinstance(explanation, str) and explanation:
        return explanation
    alt = payload.get("explanation")
    if isinstance(alt, str):
        return alt
    return ""


def _drift_type(payload: dict[str, Any]) -> str:
    value = payload.get("drift_type")
    return value if isinstance(value, str) and value else "unknown"


def _resolve_vow_manifest_path() -> Path:
    if Path("/vow").exists():
        return Path("/vow/immutable_manifest.json")
    return Path("vow/immutable_manifest.json")


def _ensure_vow_manifest(manifest_path: Path) -> tuple[bool, str | None]:
    try:
        payload = ensure_vow_artifacts(manifest_path=manifest_path)
    except Exception as exc:  # pragma: no cover - exercised via caller behavior
        return (False, f"failed to generate vow immutable manifest at {manifest_path}: {exc}")
    if not bool(payload.get("manifest_present")):
        return (False, f"vow immutable manifest missing at {manifest_path}")
    return (True, None)


def _run_audit_immutability_verifier(manifest_path: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "scripts.audit_immutability_verifier",
        "--manifest",
        str(manifest_path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    payload = _read_json(Path("glow/audits/audit_immutability_result.json"))
    if completed.returncode == 0:
        return {
            "domain": "audit_immutability",
            "baseline_present": True,
            "drift_type": "none",
            "drift_explanation": None,
            "drifted": False,
            "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_VOW_MANIFEST_DRIFT",
        }

    explanation = "audit immutability verifier failed"
    if isinstance(payload, dict):
        error = payload.get("error")
        issues = payload.get("issues")
        if isinstance(error, str) and error:
            explanation = error
        elif isinstance(issues, list) and issues:
            explanation = "; ".join(str(issue) for issue in issues)
    elif completed.stderr.strip():
        explanation = completed.stderr.strip()

    return {
        "domain": "audit_immutability",
        "baseline_present": True,
        "drift_type": "verification_failed",
        "drift_explanation": explanation,
        "drifted": True,
        "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_VOW_MANIFEST_DRIFT",
    }


def run_contract_drift(*, from_existing_reports: bool = False) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    manifest_path = _resolve_vow_manifest_path()
    manifest_ok, manifest_error = _ensure_vow_manifest(manifest_path)
    if manifest_ok:
        results.append(
            {
                "domain": "vow_manifest",
                "baseline_present": True,
                "drift_type": "none",
                "drift_explanation": None,
                "drifted": False,
                "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_VOW_MANIFEST_DRIFT",
            }
        )
        if from_existing_reports:
            verification_payload = _read_json(Path("glow/audits/audit_immutability_result.json"))
            result_ok = bool(verification_payload.get("ok", False))
            results.append(
                {
                    "domain": "audit_immutability",
                    "baseline_present": True,
                    "drift_type": "none" if result_ok else "verification_failed",
                    "drift_explanation": None if result_ok else (verification_payload or {}).get("error"),
                    "drifted": False if result_ok else True,
                    "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_VOW_MANIFEST_DRIFT",
                }
            )
        else:
            results.append(_run_audit_immutability_verifier(manifest_path))
    else:
        results.append(
            {
                "domain": "vow_manifest",
                "baseline_present": False,
                "drift_type": "preflight_failed",
                "drift_explanation": manifest_error,
                "drifted": None,
                "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_VOW_MANIFEST_DRIFT",
            }
        )
        results.append(
            {
                "domain": "audit_immutability",
                "baseline_present": False,
                "drift_type": "preflight_required",
                "drift_explanation": "vow immutable manifest missing; run make vow-manifest",
                "drifted": None,
                "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_VOW_MANIFEST_DRIFT",
            }
        )

    for domain in DRIFT_DOMAINS:
        if not domain.baseline_path.exists():
            results.append(
                {
                    "domain": domain.name,
                    "baseline_present": False,
                    "drift_type": "baseline_missing",
                    "drift_explanation": None,
                    "drifted": None,
                    "strict_gate_envvar": domain.strict_gate_envvar,
                }
            )
            continue

        if from_existing_reports:
            payload = _read_json(domain.report_path) if domain.report_path.exists() else {}
        else:
            payload = domain.detector()

        results.append(
            {
                "domain": domain.name,
                "baseline_present": True,
                "drift_type": _drift_type(payload),
                "drift_explanation": _drift_explanation(payload),
                "drifted": bool(payload.get("drifted", False)),
                "strict_gate_envvar": domain.strict_gate_envvar,
            }
        )
    return results


def _should_fail_strict(results: list[dict[str, Any]]) -> bool:
    return any(str(result.get("drift_type", "none")) not in {"none", "baseline_missing"} for result in results)


def _print_summary(results: list[dict[str, Any]]) -> None:
    print("[contract-drift] summary")
    for result in results:
        explanation = result.get("drift_explanation")
        if explanation is None:
            explanation = ""
        print(
            " - "
            f"{result['domain']}: "
            f"drift_type={result.get('drift_type', 'unknown')} "
            f"drift_explanation={explanation}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run contract drift detectors with compact summary output")
    parser.add_argument(
        "--from-existing-reports",
        action="store_true",
        help="read pre-generated drift reports instead of invoking drift detectors",
    )
    args = parser.parse_args(argv)

    results = run_contract_drift(from_existing_reports=args.from_existing_reports)
    _print_summary(results)

    strict = os.getenv("STRICT") == "1"
    if strict and _should_fail_strict(results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
