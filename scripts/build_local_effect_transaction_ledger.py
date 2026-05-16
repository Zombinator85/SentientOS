#!/usr/bin/env python3
"""Build a metadata-only local effect transaction ledger from record files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.local_effect_transaction_ledger import (  # noqa: E402
    build_transaction_ledger_from_local_diagnostic_records,
    summarize_local_effect_transaction_ledger,
    summarize_local_effect_transaction_lifecycle_report,
    summarize_local_effect_transaction_ledger_artifact_receipt,
    validate_local_effect_transaction_ledger,
    validate_local_effect_transaction_lifecycle_report,
    write_local_effect_transaction_ledger_artifact,
)


def _load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def _unsafe_output(path_text: str) -> str | None:
    path = Path(path_text).expanduser()
    if not str(path_text).strip():
        return "output path is required"
    if path == Path(path.anchor) or path.resolve() == Path(path.anchor).resolve():
        return "refusing to write ledger artifact to filesystem root"
    if path.exists() and path.is_dir():
        return "refusing to write ledger artifact to a directory"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only local diagnostic effect transaction ledger")
    parser.add_argument("--effect-receipt", required=True, help="path to effect_receipt.json")
    parser.add_argument("--postcondition-check", required=True, help="path to postcondition_check.json")
    parser.add_argument("--production-audit", required=True, help="path to production_audit.json")
    parser.add_argument("--rollback-plan", required=True, help="path to rollback_plan.json")
    parser.add_argument("--rollback-receipt", help="path to rollback_receipt.json")
    parser.add_argument("--rollback-postcondition-check", help="path to rollback_postcondition_check.json")
    parser.add_argument("--rollback-audit", help="path to rollback_audit.json")
    parser.add_argument("--output", help="optional explicit local ledger artifact path")
    parser.add_argument("--summary", action="store_true", help="print compact summary")
    parser.add_argument("--force", action="store_true", help="overwrite --output if it already exists")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00", help="deterministic timestamp for records")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    if args.output:
        reason = _unsafe_output(args.output)
        if reason:
            print(reason, file=sys.stderr)
            return 2

    try:
        bundle = build_transaction_ledger_from_local_diagnostic_records(
            effect_receipt=_load_json(args.effect_receipt),
            postcondition_check=_load_json(args.postcondition_check),
            production_audit=_load_json(args.production_audit),
            rollback_plan=_load_json(args.rollback_plan),
            exact_rollback_receipt=_load_json(args.rollback_receipt) if args.rollback_receipt else None,
            rollback_postcondition_check=_load_json(args.rollback_postcondition_check) if args.rollback_postcondition_check else None,
            rollback_audit=_load_json(args.rollback_audit) if args.rollback_audit else None,
            created_at=args.created_at,
        )
        ledger_validation = validate_local_effect_transaction_ledger(bundle.ledger)
        report_validation = validate_local_effect_transaction_lifecycle_report(bundle.lifecycle_report)
        if not ledger_validation.ok or not report_validation.ok:
            print("local effect transaction ledger validation failed: " + ", ".join(ledger_validation.findings + report_validation.findings), file=sys.stderr)
            return 2
        artifact_receipt = None
        if args.output:
            artifact_receipt = write_local_effect_transaction_ledger_artifact(bundle.ledger, args.output, lifecycle_report=bundle.lifecycle_report, created_at=args.created_at, force=args.force)
        payload: dict[str, Any]
        if args.summary:
            payload = {
                "ledger": summarize_local_effect_transaction_ledger(bundle.ledger),
                "lifecycle_report": summarize_local_effect_transaction_lifecycle_report(bundle.lifecycle_report),
                "artifact_receipt": summarize_local_effect_transaction_ledger_artifact_receipt(artifact_receipt) if artifact_receipt else None,
                "metadata_only": True,
                "performs_no_new_effect": True,
                "host_mutation_performed": False,
                "network_performed": False,
                "provider_invocation_performed": False,
                "prompt_assembly_performed": False,
                "subprocess_performed": False,
                "shell_performed": False,
            }
        else:
            payload = {
                "ledger": bundle.ledger.to_dict(),
                "lifecycle_report": bundle.lifecycle_report.to_dict(),
                "artifact_receipt": artifact_receipt.to_dict() if artifact_receipt else None,
            }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError, FileExistsError) as exc:
        print(f"local effect transaction ledger failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
