#!/usr/bin/env python3
"""Run the bounded built-in runner transaction orchestrator in-process."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.builtin_runner_transaction_orchestrator import (  # noqa: E402
    TRANSACTION_MODES,
    run_builtin_runner_transaction_wing,
    summarize_builtin_runner_transaction_wing,
)
from sentientos.local_diagnostic_effect import DEFAULT_ARTIFACT_NAME  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bounded built-in runner local diagnostic transaction orchestrator")
    parser.add_argument("--output-dir", required=True, help="directory for the local diagnostic artifact transaction")
    parser.add_argument("--artifact-name", default=DEFAULT_ARTIFACT_NAME, help="diagnostic artifact name")
    parser.add_argument("--mode", default="diagnostic_write_only", choices=TRANSACTION_MODES, help="bounded transaction mode")
    parser.add_argument("--ledger-output", help="optional explicit ledger artifact path for *_with_ledger modes")
    parser.add_argument("--force", action="store_true", help="allow overwriting diagnostic/ledger artifacts where underlying checks permit")
    parser.add_argument("--dry-run", action="store_true", help="validate plan/request only; do not write, rollback, or write ledger artifacts")
    parser.add_argument("--summary", action="store_true", help="print compact summary")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00", help="deterministic timestamp for records")
    args = parser.parse_args(argv)

    if args.ledger_output and "ledger" not in args.mode:
        parser.error("--ledger-output is only allowed with *_with_ledger modes")

    records = run_builtin_runner_transaction_wing(
        output_dir=args.output_dir,
        artifact_name=args.artifact_name,
        transaction_mode=args.mode,
        ledger_output_path=args.ledger_output,
        force=args.force,
        dry_run=args.dry_run,
        created_at=args.created_at,
    )
    payload = summarize_builtin_runner_transaction_wing(records) if args.summary else {
        "policy": records.policy.to_dict(),
        "plan": records.plan.to_dict(),
        "request": records.request.to_dict(),
        "result": records.result.to_dict() if records.result else None,
        "receipt": records.receipt.to_dict() if records.receipt else None,
        "closure_report": records.closure_report.to_dict() if records.closure_report else None,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if records.result is None:
        return 1
    if args.dry_run:
        return 0
    if records.result.transaction_status in {"builtin_runner_transaction_blocked", "builtin_runner_transaction_failed", "builtin_runner_transaction_contradicted"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
