from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.detect_audit_drift import detect_drift as detect_audit_drift
from scripts.detect_federation_identity_drift import detect_drift as detect_federation_identity_drift
from scripts.detect_pulse_schema_drift import detect_drift as detect_pulse_schema_drift
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
    return json.loads(path.read_text(encoding="utf-8"))


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


def run_contract_drift(*, from_existing_reports: bool = False) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
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
    return any(
        result.get("baseline_present")
        and str(result.get("drift_type", "none")) != "none"
        for result in results
    )


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
