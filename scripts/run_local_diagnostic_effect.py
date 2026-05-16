#!/usr/bin/env python3
"""Run the explicit Tier-1 local diagnostic effect pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.local_diagnostic_effect import (  # noqa: E402
    DEFAULT_ARTIFACT_NAME,
    build_local_diagnostic_effect_request,
    run_local_diagnostic_effect_wing,
    summarize_local_diagnostic_effect_wing,
    validate_local_diagnostic_effect_request,
)


def _compact_summary(summary: dict[str, object], *, dry_run: bool) -> dict[str, object]:
    result = summary["result"]  # type: ignore[index]
    receipt = summary["receipt"]  # type: ignore[index]
    postcondition = summary["postcondition_check"]  # type: ignore[index]
    rollback = summary["rollback_receipt"]  # type: ignore[index]
    audit = summary["production_audit_receipt"]  # type: ignore[index]
    return {
        "dry_run": dry_run,
        "effect_status": result["effect_status"],
        "output_path": result["output_path"],
        "artifact_digest": result["artifact_digest"],
        "byte_count": result["byte_count"],
        "real_effect_performed": result["real_effect_performed"],
        "local_file_write_performed": result["local_file_write_performed"],
        "host_mutation_performed": result["host_mutation_performed"],
        "real_effect_receipt_created": receipt["real_effect_receipt_created"],
        "postcondition_status": postcondition["postcondition_status"],
        "rollback_status": rollback["rollback_status"],
        "real_rollback_performed": rollback["real_rollback_performed"],
        "file_delete_performed": rollback["file_delete_performed"],
        "audit_status": audit["audit_status"],
        "fan_pwm_write_performed": receipt["fan_pwm_write_performed"],
        "thermal_actuation_performed": receipt["thermal_actuation_performed"],
        "power_profile_mutation_performed": receipt["power_profile_mutation_performed"],
        "service_restart_performed": receipt["service_restart_performed"],
        "file_cleanup_performed": receipt["file_cleanup_performed"],
        "network_performed": receipt["network_performed"],
        "provider_invocation_performed": receipt["provider_invocation_performed"],
        "prompt_assembly_performed": receipt["prompt_assembly_performed"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write one explicit local diagnostic artifact and emit auditable receipts")
    parser.add_argument("--output-dir", required=True, help="explicit local output directory for the diagnostic artifact")
    parser.add_argument("--artifact-name", default=DEFAULT_ARTIFACT_NAME, help="single artifact filename, not a path")
    parser.add_argument("--force", action="store_true", help="allow overwriting only the named target artifact")
    parser.add_argument("--summary", action="store_true", help="print compact summary instead of full wing records")
    parser.add_argument("--dry-run", action="store_true", help="validate and summarize without writing the artifact")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00", help="deterministic timestamp for records")
    args = parser.parse_args(argv)

    request = build_local_diagnostic_effect_request(
        output_dir=args.output_dir,
        artifact_name=args.artifact_name,
        force_overwrite=args.force,
        created_at=args.created_at,
    )
    validation = validate_local_diagnostic_effect_request(request)
    if not validation.ok:
        print("local diagnostic effect request rejected: " + ", ".join(validation.findings), file=sys.stderr)
        return 2

    records = run_local_diagnostic_effect_wing(
        output_dir=args.output_dir,
        artifact_name=args.artifact_name,
        force_overwrite=args.force,
        dry_run=args.dry_run,
        created_at=args.created_at,
    )
    summary = summarize_local_diagnostic_effect_wing(records)
    if records.result.effect_status == "local_diagnostic_effect_performed" and not args.dry_run:
        output_dir = Path(args.output_dir).expanduser()
        (output_dir / "effect_receipt.json").write_text(json.dumps(records.receipt.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output_dir / "postcondition_check.json").write_text(json.dumps(records.postcondition_check.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output_dir / "production_audit.json").write_text(json.dumps(records.production_audit_receipt.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output_dir / "rollback_plan.json").write_text(json.dumps(records.rollback_plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    payload = _compact_summary(summary, dry_run=args.dry_run) if args.summary else {
        "request": records.request.to_dict(),
        "result": records.result.to_dict(),
        "receipt": records.receipt.to_dict(),
        "postcondition_check": records.postcondition_check.to_dict(),
        "rollback_plan": records.rollback_plan.to_dict(),
        "rollback_receipt": records.rollback_receipt.to_dict(),
        "production_audit_receipt": records.production_audit_receipt.to_dict(),
        "effect_receipt_path": str(Path(args.output_dir).expanduser() / "effect_receipt.json") if records.result.effect_status == "local_diagnostic_effect_performed" and not args.dry_run else None,
        "postcondition_check_path": str(Path(args.output_dir).expanduser() / "postcondition_check.json") if records.result.effect_status == "local_diagnostic_effect_performed" and not args.dry_run else None,
        "production_audit_path": str(Path(args.output_dir).expanduser() / "production_audit.json") if records.result.effect_status == "local_diagnostic_effect_performed" and not args.dry_run else None,
        "rollback_plan_path": str(Path(args.output_dir).expanduser() / "rollback_plan.json") if records.result.effect_status == "local_diagnostic_effect_performed" and not args.dry_run else None,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if records.result.effect_status == "local_diagnostic_effect_performed" or args.dry_run:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
