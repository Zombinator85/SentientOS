from __future__ import annotations

"""Deterministic audit convergence workflow."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from scripts import apply_audit_repairs, plan_audit_repairs, verify_audits

DEFAULT_REPORT_PATH = Path("glow/audits/audit_convergence_report.json")
DEFAULT_ITERATIONS_DIR = Path("glow/audits/convergence")
SCHEMA_VERSION = 1
MAX_MANUAL_ISSUES = 50


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(issue.get("path", "")),
        str(issue.get("code", "unknown")),
        str(issue.get("details", "")),
        str(issue.get("expected", "")),
        str(issue.get("actual", "")),
    )


def _verify_summary(target: Path) -> dict[str, Any]:
    issues_by_path, percent, _ = verify_audits.verify_audits_detailed(directory=target, quarantine=True, repair=False)
    ordered: list[dict[str, Any]] = []
    for path in sorted(issues_by_path.keys()):
        ordered.extend(sorted(issues_by_path[path], key=_issue_sort_key))

    per_code: dict[str, int] = {}
    for issue in ordered:
        code = str(issue.get("code", "unknown"))
        per_code[code] = per_code.get(code, 0) + 1

    return {
        "ok": len(ordered) == 0,
        "issues_total": len(ordered),
        "issues_per_code": dict(sorted(per_code.items())),
        "issues": ordered,
        "percent_valid": percent,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_convergence(target: Path, max_iterations: int, apply_repairs: bool) -> dict[str, Any]:
    iterations_dir = DEFAULT_ITERATIONS_DIR
    iterations_dir.mkdir(parents=True, exist_ok=True)

    before = _verify_summary(target)
    current = before
    iteration_records: list[dict[str, Any]] = []
    applied_repairs_count = 0
    quarantine_paths: set[str] = set()

    for index in range(1, max_iterations + 1):
        iter_name = f"iter_{index:02d}"
        plan_path = iterations_dir / f"{iter_name}_plan.json"
        result_path = iterations_dir / f"{iter_name}_result.json"

        plan = plan_audit_repairs.build_plan(target)
        _write_json(plan_path, plan)
        plan_audit_repairs._append_receipt("plan", plan_path, plan)

        iter_record: dict[str, Any] = {
            "iteration": iter_name,
            "plan_path": str(plan_path),
            "result_path": None,
            "applied_count": 0,
            "stopped_reason": None,
        }

        if not apply_repairs:
            iter_record["stopped_reason"] = "no_apply_mode"
            iteration_records.append(iter_record)
            break

        result = apply_audit_repairs.apply_repairs(plan, plan_path)
        _write_json(result_path, result)
        apply_audit_repairs._append_receipt("result", result_path, result)

        iter_record["result_path"] = str(result_path)
        iter_record["applied_count"] = len(result.get("applied", []))
        applied_repairs_count += int(iter_record["applied_count"])

        for quarantine_path in sorted(str(path) for path in result.get("quarantine_paths", [])):
            quarantine_paths.add(quarantine_path)

        iteration_records.append(iter_record)
        current = _verify_summary(target)

        if current["ok"]:
            iter_record["stopped_reason"] = "clean"
            break
        if not result.get("applied"):
            iter_record["stopped_reason"] = "no_changes_applied"
            break

    manual_repairs: list[dict[str, Any]] = []
    final_plan = plan_audit_repairs.build_plan(target)
    for repair in final_plan.get("repairs", []):
        if not repair.get("safe", False):
            manual_repairs.append(
                {
                    "repair_id": repair.get("repair_id"),
                    "paths": sorted(str(path) for path in repair.get("paths", [])),
                    "reason_codes": sorted(str(code) for code in repair.get("reason_codes", [])),
                    "action": repair.get("action"),
                }
            )

    manual_repairs = sorted(
        manual_repairs,
        key=lambda item: (
            str(item.get("repair_id", "")),
            ",".join(item.get("paths", [])),
            ",".join(item.get("reason_codes", [])),
        ),
    )

    after = current
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "target": str(target),
        "max_iterations": max_iterations,
        "iterations": iteration_records,
        "counts_before": {
            "issues_total": before["issues_total"],
            "issues_per_code": before["issues_per_code"],
        },
        "counts_after": {
            "issues_total": after["issues_total"],
            "issues_per_code": after["issues_per_code"],
        },
        "applied_repairs": applied_repairs_count,
        "remaining_manual_issues": manual_repairs[:MAX_MANUAL_ISSUES],
        "quarantine_paths": sorted(quarantine_paths),
        "ok": bool(after["ok"]),
        "no_safe_repairs_remaining": not bool(final_plan.get("ok_to_apply", False)),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Converge audit repairs deterministically")
    parser.add_argument("target_dir", nargs="?", default="logs/", help="audit log directory")
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--no-apply", action="store_true", help="plan and verify only; do not mutate logs")
    args = parser.parse_args(argv)

    target = Path(args.target_dir)
    report = run_convergence(target=target, max_iterations=args.max_iterations, apply_repairs=not args.no_apply)

    output = Path(args.output)
    _write_json(output, report)
    print(json.dumps({"tool": "converge_audits", "path": str(output), "ok": report["ok"]}, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
