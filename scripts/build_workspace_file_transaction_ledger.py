#!/usr/bin/env python3
"""Build a metadata-only workspace file transaction ledger from explicit JSON records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.workspace_file_transaction_ledger import (  # noqa: E402
    DEFAULT_CREATED_AT,
    build_transaction_ledger_from_workspace_file_records,
    summarize_workspace_file_transaction_ledger,
    summarize_workspace_file_transaction_lifecycle_report,
    summarize_workspace_file_transaction_ledger_artifact_receipt,
    write_workspace_file_transaction_ledger_artifact,
)


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only ledger for one workspace-scoped file effect transaction.")
    parser.add_argument("--effect-receipt", required=True)
    parser.add_argument("--preimage", required=True)
    parser.add_argument("--postcondition-check", required=True)
    parser.add_argument("--production-audit", required=True)
    parser.add_argument("--rollback-plan", required=True)
    parser.add_argument("--effect-request")
    parser.add_argument("--effect-result")
    parser.add_argument("--rollback-receipt")
    parser.add_argument("--rollback-result")
    parser.add_argument("--rollback-postcondition-check")
    parser.add_argument("--rollback-audit")
    parser.add_argument("--output")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    args = parser.parse_args(argv)

    bundle = build_transaction_ledger_from_workspace_file_records(
        effect_request=_load(args.effect_request) if args.effect_request else None,
        effect_result=_load(args.effect_result) if args.effect_result else None,
        preimage=_load(args.preimage),
        effect_receipt=_load(args.effect_receipt),
        postcondition_check=_load(args.postcondition_check),
        production_audit=_load(args.production_audit),
        rollback_plan=_load(args.rollback_plan),
        rollback_result=_load(args.rollback_result) if args.rollback_result else None,
        rollback_receipt=_load(args.rollback_receipt) if args.rollback_receipt else None,
        rollback_postcondition_check=_load(args.rollback_postcondition_check) if args.rollback_postcondition_check else None,
        rollback_audit=_load(args.rollback_audit) if args.rollback_audit else None,
        created_at=args.created_at,
    )
    artifact_receipt = None
    if args.output:
        artifact_receipt = write_workspace_file_transaction_ledger_artifact(bundle.ledger, args.output, lifecycle_report=bundle.lifecycle_report, created_at=args.created_at, force=args.force)
    payload: dict[str, Any]
    if args.summary:
        payload = {
            "ledger": summarize_workspace_file_transaction_ledger(bundle.ledger),
            "lifecycle_report": summarize_workspace_file_transaction_lifecycle_report(bundle.lifecycle_report),
            "artifact_receipt": summarize_workspace_file_transaction_ledger_artifact_receipt(artifact_receipt) if artifact_receipt else None,
            "metadata_only": True,
            "performs_no_effect_or_rollback": True,
            "subprocess_performed": False,
            "shell_performed": False,
            "network_performed": False,
            "provider_invocation_performed": False,
            "prompt_assembly_performed": False,
        }
    else:
        payload = {
            "ledger": bundle.ledger.to_dict(),
            "lifecycle_report": bundle.lifecycle_report.to_dict(),
            "artifact_receipt": artifact_receipt.to_dict() if artifact_receipt else None,
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if bundle.ledger.ledger_status != "workspace_file_transaction_ledger_contradicted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
