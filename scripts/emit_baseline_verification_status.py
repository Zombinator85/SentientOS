from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

BLOCKING_FAILURE_CLASSES = {
    "covenant_tripwire_drift",
    "pulse_federation_persistence",
    "pulse_persistence_signature",
}
DEFERRED_FAILURE_CLASSES = {
    "bootstrap_import_instability",
    "unclassified_runtime_failure",
}
RUN_TESTS_UNAVAILABLE_EXIT_REASONS = {
    "airlock-failed",
    "install-failed",
}
RUN_TESTS_INCOMPLETE_EXIT_REASONS = {
    "bootstrap-metrics-failed",
}


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
    lane_state: str
    failure_count: int
    details: dict[str, Any]


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _run_tests_summary(
    *,
    failure_digest: Mapping[str, Any] | None,
    run_provenance: Mapping[str, Any] | None,
) -> LaneSummary:
    digest_groups = failure_digest.get("failure_groups") if isinstance(failure_digest, Mapping) else None
    digest_totals = failure_digest.get("failure_class_totals") if isinstance(failure_digest, Mapping) else None
    class_totals = (
        {str(name): int(count) for name, count in digest_totals.items() if isinstance(count, int)}
        if isinstance(digest_totals, dict)
        else {}
    )
    failure_groups = digest_groups if isinstance(digest_groups, list) else []
    provenance = run_provenance if isinstance(run_provenance, Mapping) else {}
    exit_reason = str(provenance.get("exit_reason") or "")
    metrics_status = str(provenance.get("metrics_status") or "unknown")
    execution_mode = str(provenance.get("execution_mode") or "unknown")
    pytest_exit_code = _int_or_none(provenance.get("pytest_exit_code"))
    tests_failed = _int_or_none(provenance.get("tests_failed"))
    run_intent = str(provenance.get("run_intent") or "unknown")
    blocking_classes = sorted(name for name in class_totals if name in BLOCKING_FAILURE_CLASSES and class_totals[name] > 0)
    deferred_classes = sorted(name for name in class_totals if name not in BLOCKING_FAILURE_CLASSES and class_totals[name] > 0)

    details: dict[str, Any] = {
        "failure_group_count": len(failure_groups),
        "failure_class_totals": class_totals,
        "blocking_failure_classes": blocking_classes,
        "deferred_failure_classes": deferred_classes,
        "run_intent": run_intent,
        "execution_mode": execution_mode,
        "metrics_status": metrics_status,
        "exit_reason": exit_reason or None,
    }
    if pytest_exit_code is not None:
        details["pytest_exit_code"] = pytest_exit_code

    if not provenance and not failure_groups:
        return LaneSummary("missing", "lane_not_run", 0, {**details, "reason": "run_tests_artifacts_missing"})

    if exit_reason in RUN_TESTS_UNAVAILABLE_EXIT_REASONS:
        return LaneSummary("amber", "lane_unavailable_in_environment", 0, details)

    if exit_reason in RUN_TESTS_INCOMPLETE_EXIT_REASONS or metrics_status in {"partial", "unavailable"}:
        return LaneSummary("amber", "lane_incomplete", len(failure_groups), details)

    if execution_mode != "execute":
        return LaneSummary("amber", "lane_not_run", 0, details)

    if failure_groups:
        if blocking_classes:
            return LaneSummary("red", "lane_completed_with_blocking_failure", len(failure_groups), details)
        return LaneSummary("amber", "lane_completed_with_deferred_debt", len(failure_groups), details)

    if (pytest_exit_code is not None and pytest_exit_code != 0) or (tests_failed is not None and tests_failed > 0):
        return LaneSummary("red", "lane_completed_with_blocking_failure", tests_failed or 0, details)

    return LaneSummary("green", "lane_completed_with_advisories", 0, details)


def _mypy_summary(*, output_path: Path, ratchet_status: Mapping[str, Any] | None) -> LaneSummary:
    ratchet = ratchet_status if isinstance(ratchet_status, Mapping) else {}
    ratchet_state = str(ratchet.get("status") or "")
    if ratchet:
        deferred_count = _int_or_none(ratchet.get("deferred_debt_error_count")) or 0
        ratcheted_count = _int_or_none(ratchet.get("ratcheted_new_error_count")) or 0
        protected_new = _int_or_none(ratchet.get("protected_new_error_count")) or 0
        strict_status = str(ratchet.get("policy_strict_status") or "not_run")
        details = {
            "ratchet_status": ratchet_state or "unknown",
            "deferred_debt_error_count": deferred_count,
            "ratcheted_new_error_count": ratcheted_count,
            "protected_new_error_count": protected_new,
            "policy_strict_status": strict_status,
        }
        if ratchet_state == "ok":
            if deferred_count > 0:
                return LaneSummary("amber", "lane_completed_with_deferred_debt", deferred_count, details)
            return LaneSummary("green", "lane_completed_with_advisories", 0, details)
        if ratchet_state == "new_errors" or ratcheted_count > 0 or protected_new > 0 or strict_status == "failed":
            return LaneSummary("red", "lane_completed_with_blocking_failure", max(ratcheted_count, protected_new), details)
        if ratchet_state == "baseline_refreshed":
            return LaneSummary("amber", "lane_completed_with_advisories", 0, details)
        return LaneSummary("amber", "lane_incomplete", 0, details)

    if not output_path.exists():
        return LaneSummary("missing", "lane_not_run", 0, {"reason": "mypy_artifacts_missing"})
    line = ""
    try:
        for row in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "Found " in row and " errors in " in row:
                line = row
    except OSError:
        return LaneSummary("amber", "lane_incomplete", 0, {"reason": "mypy_output_unreadable"})
    parsed = _parse_mypy_found(line)
    if parsed is None:
        return LaneSummary("amber", "lane_incomplete", 0, {"reason": "mypy_summary_not_found"})
    errors, files = parsed
    return LaneSummary(
        "green" if errors == 0 else "amber",
        "lane_completed_with_advisories" if errors == 0 else "lane_completed_with_deferred_debt",
        errors,
        {
            "error_count": errors,
            "file_count": files,
            "summary_line": line,
        },
    )


def _corridor_summary(payload: Mapping[str, Any] | None) -> LaneSummary:
    if not isinstance(payload, Mapping):
        return LaneSummary("missing", "lane_not_run", 0, {"reason": "protected_corridor_report_missing"})
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
        lane_state = "lane_completed_with_blocking_failure" if lane_status == "red" else "lane_completed_with_advisories"
        return LaneSummary(lane_status, lane_state, blocking_count, details)

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
        lane_state = "lane_completed_with_blocking_failure" if lane_status == "red" else "lane_completed_with_advisories"
        return LaneSummary(
            lane_status,
            lane_state,
            blocking_count,
            {
                "reported_status": "derived_from_profiles",
                "profile_count": len(profiles),
                "blocking_failures": blocking_count,
                "advisory_or_debt_count": advisory_count,
            },
        )

    return LaneSummary("unknown", "lane_incomplete", 0, {"reason": "protected_corridor_schema_unrecognized"})


def build_status(
    *,
    failure_digest_path: Path,
    run_provenance_path: Path,
    mypy_output_path: Path,
    mypy_ratchet_status_path: Path,
    corridor_report_path: Path,
) -> dict[str, Any]:
    failure_digest = _read_json(failure_digest_path)
    run_provenance = _read_json(run_provenance_path)
    mypy_ratchet_status = _read_json(mypy_ratchet_status_path)
    corridor_payload = _read_json(corridor_report_path)

    run_tests = _run_tests_summary(failure_digest=failure_digest, run_provenance=run_provenance)
    mypy = _mypy_summary(output_path=mypy_output_path, ratchet_status=mypy_ratchet_status)
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
        "lane_state_taxonomy": {
            "lane_not_run": "no evidence that the lane executed in this cycle",
            "lane_unavailable_in_environment": "lane could not run because required environment/bootstrap dependencies were unavailable",
            "lane_incomplete": "lane started but output artifacts are incomplete/unreadable",
            "lane_completed_with_advisories": "lane completed and contains no blocking findings",
            "lane_completed_with_deferred_debt": "lane completed and only deferred debt remains",
            "lane_completed_with_blocking_failure": "lane completed and found blocking failures",
        },
        "lanes": {
            "protected_corridor": {
                "status": protected_corridor.status,
                "lane_state": protected_corridor.lane_state,
                "details": protected_corridor.details,
            },
            "run_tests": {
                "status": run_tests.status,
                "lane_state": run_tests.lane_state,
                "failure_count": run_tests.failure_count,
                "details": run_tests.details,
            },
            "mypy": {
                "status": mypy.status,
                "lane_state": mypy.lane_state,
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
        "--run-provenance",
        type=Path,
        default=Path("glow/test_runs/test_run_provenance.json"),
    )
    parser.add_argument(
        "--mypy-output",
        type=Path,
        default=Path("glow/typecheck/mypy_latest.txt"),
    )
    parser.add_argument(
        "--mypy-ratchet-status",
        type=Path,
        default=Path("glow/contracts/typing_ratchet_status.json"),
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
        run_provenance_path=args.run_provenance,
        mypy_output_path=args.mypy_output,
        mypy_ratchet_status_path=args.mypy_ratchet_status,
        corridor_report_path=args.protected_corridor_report,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
