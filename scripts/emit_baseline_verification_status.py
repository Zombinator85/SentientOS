from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _parse_mypy_found(line: str) -> tuple[int, int] | None:
    match = re.search(r"Found\s+(\d+)\s+errors\s+in\s+(\d+)\s+files", line)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


@dataclass(frozen=True)
class LaneSummary:
    status: str
    failure_count: int
    details: dict[str, Any]


def _run_tests_summary(payload: Mapping[str, Any] | None) -> LaneSummary:
    if not isinstance(payload, Mapping):
        return LaneSummary("missing", 0, {"reason": "test_failure_digest_missing"})
    groups = payload.get("failure_groups")
    if not isinstance(groups, list):
        return LaneSummary("unknown", 0, {"reason": "failure_groups_missing"})
    failures = len(groups)
    class_totals = payload.get("failure_class_totals")
    details = {
        "failure_group_count": failures,
        "failure_class_totals": class_totals if isinstance(class_totals, dict) else {},
    }
    return LaneSummary("green" if failures == 0 else "red", failures, details)


def _mypy_summary(output_path: Path) -> LaneSummary:
    if not output_path.exists():
        return LaneSummary("missing", 0, {"reason": "mypy_output_missing"})
    line = ""
    try:
        for row in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "Found " in row and " errors in " in row:
                line = row
    except OSError:
        return LaneSummary("missing", 0, {"reason": "mypy_output_unreadable"})
    parsed = _parse_mypy_found(line)
    if parsed is None:
        return LaneSummary("unknown", 0, {"reason": "mypy_summary_not_found"})
    errors, files = parsed
    return LaneSummary(
        "green" if errors == 0 else "red",
        errors,
        {
            "error_count": errors,
            "file_count": files,
            "summary_line": line,
        },
    )


def _corridor_summary(payload: Mapping[str, Any] | None) -> LaneSummary:
    if not isinstance(payload, Mapping):
        return LaneSummary("missing", 0, {"reason": "protected_corridor_report_missing"})
    global_summary = payload.get("global_summary")
    if isinstance(global_summary, Mapping):
        reported_status = str(global_summary.get("status") or "unknown")
        blocking_profiles = global_summary.get("blocking_profiles")
        blocking_count = len(blocking_profiles) if isinstance(blocking_profiles, list) else 0
        details = {
            "reported_status": reported_status,
            "blocking_profiles": blocking_profiles if isinstance(blocking_profiles, list) else [],
            "advisory_profiles": global_summary.get("advisory_profiles") if isinstance(global_summary.get("advisory_profiles"), list) else [],
            "debt_profiles": global_summary.get("debt_profiles") if isinstance(global_summary.get("debt_profiles"), list) else [],
            "corridor_blocking": bool(global_summary.get("corridor_blocking", False)),
        }
        if reported_status == "green":
            lane_status = "green"
        elif reported_status == "amber":
            lane_status = "amber"
        else:
            lane_status = "red"
        return LaneSummary(lane_status, blocking_count, details)

    profiles = payload.get("profiles")
    if isinstance(profiles, list) and profiles:
        blocking_count = 0
        advisory_count = 0
        for profile in profiles:
            if not isinstance(profile, Mapping):
                continue
            summary = profile.get("summary")
            if not isinstance(summary, Mapping):
                continue
            blocking_count += int(summary.get("blocking_failure_count", 0))
            blocking_count += int(summary.get("provisioning_failure_count", 0))
            blocking_count += int(summary.get("command_unavailable_count", 0))
            advisory_count += int(summary.get("policy_skip_count", 0))
            advisory_count += int(summary.get("advisory_warning_count", 0))
            advisory_count += int(summary.get("non_blocking_failure_count", 0))
        if blocking_count > 0:
            lane_status = "red"
        elif advisory_count > 0:
            lane_status = "amber"
        else:
            lane_status = "green"
        return LaneSummary(
            lane_status,
            blocking_count,
            {
                "reported_status": "derived_from_profiles",
                "profile_count": len(profiles),
                "blocking_failures": blocking_count,
                "advisory_or_debt_count": advisory_count,
            },
        )

    return LaneSummary("unknown", 0, {"reason": "protected_corridor_schema_unrecognized"})


def build_status(
    *,
    failure_digest_path: Path,
    mypy_output_path: Path,
    corridor_report_path: Path,
) -> dict[str, Any]:
    failure_digest = _read_json(failure_digest_path)
    corridor_payload = _read_json(corridor_report_path)

    run_tests = _run_tests_summary(failure_digest)
    mypy = _mypy_summary(mypy_output_path)
    protected_corridor = _corridor_summary(corridor_payload)

    broad_green = run_tests.status == "green" and mypy.status == "green"
    protected_green = protected_corridor.status in {"green", "amber"}

    blocking_classes: list[str] = []
    deferred_classes: list[str] = []
    class_totals = {}
    if isinstance(failure_digest, Mapping):
        raw_totals = failure_digest.get("failure_class_totals")
        if isinstance(raw_totals, Mapping):
            class_totals = {str(k): int(v) for k, v in raw_totals.items() if isinstance(v, int)}
    for failure_class, count in class_totals.items():
        if count <= 0:
            continue
        if failure_class in {"covenant_tripwire_drift", "pulse_federation_persistence", "pulse_persistence_signature"}:
            blocking_classes.append(failure_class)
        else:
            deferred_classes.append(failure_class)

    return {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "protected_corridor_green": protected_green,
        "broad_baseline_green": broad_green,
        "lanes": {
            "protected_corridor": {
                "status": protected_corridor.status,
                "details": protected_corridor.details,
            },
            "run_tests": {
                "status": run_tests.status,
                "failure_count": run_tests.failure_count,
                "details": run_tests.details,
            },
            "mypy": {
                "status": mypy.status,
                "failure_count": mypy.failure_count,
                "details": mypy.details,
            },
        },
        "classification": {
            "failure_class_totals": class_totals,
            "blocking_failure_classes": sorted(set(blocking_classes)),
            "deferred_failure_classes": sorted(set(deferred_classes)),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit baseline-wide verification lane status summary.")
    parser.add_argument(
        "--failure-digest",
        type=Path,
        default=Path("glow/test_runs/test_failure_digest.json"),
    )
    parser.add_argument(
        "--mypy-output",
        type=Path,
        default=Path("glow/typecheck/mypy_latest.txt"),
    )
    parser.add_argument(
        "--protected-corridor-report",
        type=Path,
        default=Path("glow/contracts/protected_corridor_report.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("glow/contracts/baseline_verification_status.json"),
    )
    args = parser.parse_args(argv)

    payload = build_status(
        failure_digest_path=args.failure_digest,
        mypy_output_path=args.mypy_output,
        corridor_report_path=args.protected_corridor_report,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
