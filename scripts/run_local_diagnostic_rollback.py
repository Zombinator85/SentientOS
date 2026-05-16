#!/usr/bin/env python3
"""Run the explicit exact-artifact local diagnostic rollback pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.local_diagnostic_effect import (  # noqa: E402
    build_local_diagnostic_exact_rollback_request,
    perform_local_diagnostic_exact_rollback,
    build_local_diagnostic_exact_rollback_receipt,
    perform_local_diagnostic_rollback_postcondition_check,
    build_local_diagnostic_rollback_audit_receipt,
    run_local_diagnostic_exact_rollback_wing,
    summarize_local_diagnostic_exact_rollback_wing,
    validate_local_diagnostic_exact_rollback_request,
)


def _load_json(path: str) -> dict[str, object]:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def _compact(summary: dict[str, object], *, dry_run: bool) -> dict[str, object]:
    request = summary["request"]  # type: ignore[index]
    result = summary["result"]  # type: ignore[index]
    receipt = summary["receipt"]  # type: ignore[index]
    postcondition = summary["postcondition_check"]  # type: ignore[index]
    audit = summary["rollback_audit_receipt"]  # type: ignore[index]
    return {
        "dry_run": dry_run,
        "request_status": request["request_status"],
        "output_path": result["output_path"],
        "would_delete_exact_artifact": dry_run and request["request_status"] == "local_diagnostic_exact_rollback_requested",
        "rollback_status": result["rollback_status"],
        "real_rollback_performed": result["real_rollback_performed"],
        "file_delete_performed": result["file_delete_performed"],
        "host_mutation_performed": result["host_mutation_performed"],
        "exact_artifact_only": receipt["exact_artifact_only"],
        "general_cleanup_performed": receipt["general_cleanup_performed"],
        "directory_cleanup_performed": receipt["directory_cleanup_performed"],
        "recursive_delete_performed": receipt["recursive_delete_performed"],
        "wildcard_delete_performed": receipt["wildcard_delete_performed"],
        "unrelated_file_delete_performed": receipt["unrelated_file_delete_performed"],
        "postcondition_status": postcondition["postcondition_status"],
        "observed_exists": postcondition["observed_exists"],
        "audit_status": audit["audit_status"],
        "audit_for_exact_local_diagnostic_artifact_only": audit["audit_for_exact_local_diagnostic_artifact_only"],
        "network_performed": receipt["network_performed"],
        "provider_invocation_performed": receipt["provider_invocation_performed"],
        "prompt_assembly_performed": receipt["prompt_assembly_performed"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete only the exact local diagnostic artifact proven by receipt and rollback plan")
    parser.add_argument("--effect-receipt", required=True, help="path to effect_receipt.json from the local diagnostic effect pilot")
    parser.add_argument("--rollback-plan", required=True, help="path to rollback_plan.json from the local diagnostic effect pilot")
    parser.add_argument("--output-dir-scope", required=True, help="explicit directory scope containing the exact artifact")
    parser.add_argument("--allow-missing-artifact", action="store_true", help="record no deletion if the exact artifact is already absent")
    parser.add_argument("--summary", action="store_true", help="print compact summary instead of full rollback records")
    parser.add_argument("--dry-run", action="store_true", help="validate and report the exact artifact path without deleting it")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00", help="deterministic timestamp for records")
    args = parser.parse_args(argv)

    effect_receipt = _load_json(args.effect_receipt)
    rollback_plan = _load_json(args.rollback_plan)
    request = build_local_diagnostic_exact_rollback_request(
        effect_receipt,
        rollback_plan,
        output_dir_scope=args.output_dir_scope,
        allow_missing_artifact=args.allow_missing_artifact,
        created_at=args.created_at,
    )
    validation = validate_local_diagnostic_exact_rollback_request(request)
    if not validation.ok:
        print("local diagnostic exact rollback request rejected: " + ", ".join(validation.findings), file=sys.stderr)
        return 2

    records = run_local_diagnostic_exact_rollback_wing(
        effect_receipt,
        rollback_plan,
        output_dir_scope=args.output_dir_scope,
        allow_missing_artifact=args.allow_missing_artifact,
        dry_run=args.dry_run,
        created_at=args.created_at,
    )
    summary = summarize_local_diagnostic_exact_rollback_wing(records)
    payload = _compact(summary, dry_run=args.dry_run) if args.summary else {
        "request": records.request.to_dict(),
        "result": records.result.to_dict(),
        "receipt": records.receipt.to_dict(),
        "postcondition_check": records.postcondition_check.to_dict(),
        "rollback_audit_receipt": records.audit_receipt.to_dict(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.dry_run:
        return 0
    if records.result.rollback_status in {"local_diagnostic_exact_rollback_performed", "local_diagnostic_exact_rollback_missing_artifact"} and (records.result.real_rollback_performed or args.allow_missing_artifact):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
