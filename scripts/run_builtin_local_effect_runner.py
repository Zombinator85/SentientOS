#!/usr/bin/env python3
"""Run the bounded built-in local effect runner pilot in-process."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.builtin_local_effect_runner import (  # noqa: E402
    RUNNER_ACTION_KINDS,
    run_builtin_local_effect_runner_wing,
    summarize_builtin_local_effect_runner_wing,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bounded built-in local diagnostic effect / exact rollback runner")
    parser.add_argument("--action", required=True, choices=RUNNER_ACTION_KINDS, help="bounded built-in runner action kind")
    parser.add_argument("--output-dir", help="output directory for local_diagnostic_artifact_write")
    parser.add_argument("--artifact-name", help="optional diagnostic artifact name")
    parser.add_argument("--force", action="store_true", help="allow overwriting the diagnostic artifact for write action")
    parser.add_argument("--effect-receipt", help="effect_receipt.json for exact rollback")
    parser.add_argument("--rollback-plan", help="rollback_plan.json for exact rollback")
    parser.add_argument("--output-dir-scope", help="scope directory for exact rollback")
    parser.add_argument("--allow-missing-artifact", action="store_true", help="accepted for CLI compatibility; exact rollback still preserves underlying safety posture")
    parser.add_argument("--dry-run", action="store_true", help="validate only; do not perform underlying write/delete")
    parser.add_argument("--summary", action="store_true", help="print compact summary")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00", help="deterministic timestamp for records")
    args = parser.parse_args(argv)

    if args.action == "local_diagnostic_artifact_write" and not args.output_dir:
        parser.error("--output-dir is required for local_diagnostic_artifact_write")
    if args.action == "local_diagnostic_exact_rollback" and (not args.effect_receipt or not args.rollback_plan or not args.output_dir_scope):
        parser.error("--effect-receipt, --rollback-plan, and --output-dir-scope are required for local_diagnostic_exact_rollback")

    records = run_builtin_local_effect_runner_wing(
        action_kind=args.action,
        output_dir=args.output_dir,
        artifact_name=args.artifact_name,
        effect_receipt_path=args.effect_receipt,
        rollback_plan_path=args.rollback_plan,
        output_dir_scope=args.output_dir_scope,
        force=args.force,
        dry_run=args.dry_run,
        created_at=args.created_at,
    )
    summary = summarize_builtin_local_effect_runner_wing(records)
    payload = summary if args.summary else {
        "declaration": records.declaration.to_dict(),
        "request": records.request.to_dict(),
        "result": records.result.to_dict() if records.result else None,
        "execution_receipt": records.execution_receipt.to_dict() if records.execution_receipt else None,
        "block_receipt": records.block_receipt.to_dict() if records.block_receipt else None,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if records.block_receipt is not None:
        return 2
    if records.result is None:
        return 1
    if args.dry_run:
        return 0
    return 0 if records.result.result_status == "builtin_runner_invocation_performed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
