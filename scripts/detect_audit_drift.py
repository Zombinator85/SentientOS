from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts import converge_audits, verify_audits

SCHEMA_VERSION = 1
DEFAULT_BASELINE = Path("glow/audits/baseline/audit_baseline.json")
DEFAULT_REPORT = Path("glow/audits/audit_drift_report.json")


def _bounded(value: object) -> str:
    return str(value)[: verify_audits.MAX_ISSUE_LENGTH]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object payload in {path}")
    return payload


def _issue_tuples(issues_by_path: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
    tuples: list[dict[str, str]] = []
    for path in sorted(issues_by_path):
        for issue in issues_by_path[path]:
            tuples.append(
                {
                    "code": _bounded(issue.get("code", "unknown")),
                    "path": _bounded(issue.get("path", path)),
                    "expected": _bounded(issue.get("expected", "")),
                    "actual": _bounded(issue.get("actual", "")),
                }
            )
    return sorted(tuples, key=lambda i: (i["code"], i["path"], i["expected"], i["actual"]))


def _manifest(target: Path) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    logs = sorted(path for path in target.iterdir() if verify_audits._is_log_file(path))
    for path in logs:
        manifest.append(
            {
                "path": path.as_posix(),
                "size": path.stat().st_size,
                "hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return manifest


def _fingerprint(manifest: list[dict[str, Any]]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_drift(*, target: Path, baseline_path: Path, output_path: Path, max_iterations: int = 1) -> dict[str, Any]:
    baseline = _read_json(baseline_path)
    baseline_tuples = baseline.get("issue_tuples", [])
    if not isinstance(baseline_tuples, list):
        baseline_tuples = []

    issues_by_path, _, _ = verify_audits.verify_audits_detailed(directory=target, quarantine=True, repair=False)
    current_tuples = _issue_tuples(issues_by_path)

    baseline_set = {(str(i.get("code", "")), str(i.get("path", "")), str(i.get("expected", "")), str(i.get("actual", ""))) for i in baseline_tuples if isinstance(i, dict)}
    current_set = {(i["code"], i["path"], i["expected"], i["actual"]) for i in current_tuples}

    new_issues = sorted(current_set - baseline_set)
    resolved_issues = sorted(baseline_set - current_set)

    convergence_report = converge_audits.run_convergence(target=target, max_iterations=max_iterations, apply_repairs=False)
    convergence_path = converge_audits.DEFAULT_REPORT_PATH
    convergence_path.parent.mkdir(parents=True, exist_ok=True)
    convergence_path.write_text(json.dumps(convergence_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "baseline_fingerprint": str(baseline.get("baseline_fingerprint", "")),
        "current_fingerprint": _fingerprint(_manifest(target)),
        "drifted": bool(new_issues or resolved_issues),
        "new_issues": [
            {"code": code, "path": path, "expected": expected, "actual": actual}
            for code, path, expected, actual in new_issues
        ],
        "resolved_issues": [
            {"code": code, "path": path, "expected": expected, "actual": actual}
            for code, path, expected, actual in resolved_issues
        ],
        "new_manual_required_count": max(
            0,
            len(convergence_report.get("remaining_manual_issues", []))
            - len(baseline.get("manual_issues", [])),
        ),
        "notes": [
            f"baseline={baseline_path.as_posix()}",
            f"convergence_report={convergence_path.as_posix()}",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect audit drift against a captured baseline")
    parser.add_argument("target_dir", nargs="?", default="logs", help="audit log directory")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="baseline path")
    parser.add_argument("--output", default=str(DEFAULT_REPORT), help="drift report path")
    parser.add_argument("--max-iterations", type=int, default=1, help="max convergence planning iterations")
    args = parser.parse_args(argv)

    report = detect_drift(
        target=Path(args.target_dir),
        baseline_path=Path(args.baseline),
        output_path=Path(args.output),
        max_iterations=args.max_iterations,
    )
    print(json.dumps({"tool": "detect_audit_drift", "drifted": report["drifted"], "output": args.output}, sort_keys=True))

    if os.getenv("SENTIENTOS_CI_FAIL_ON_AUDIT_DRIFT") == "1" and report["drifted"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
