#!/usr/bin/env python3
"""Run the explicit workspace-scoped single-file update pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from sentientos.workspace_file_effect import (
    DEFAULT_CREATED_AT,
    build_workspace_file_effect_request,
    build_workspace_file_effect_receipt,
    build_workspace_file_production_audit_receipt,
    build_workspace_file_rollback_plan,
    build_workspace_file_rollback_receipt,
    perform_workspace_file_effect,
    perform_workspace_file_postcondition_check,
    perform_workspace_file_rollback,
    perform_workspace_file_rollback_postcondition_check,
    summarize_workspace_file_effect_receipt,
    summarize_workspace_file_effect_result,
    summarize_workspace_file_postcondition_check,
    summarize_workspace_file_production_audit_receipt,
    summarize_workspace_file_rollback_receipt,
    summarize_workspace_file_rollback_result,
    validate_workspace_file_effect_request,
)


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or update exactly one explicit file inside an explicit workspace root.")
    parser.add_argument("--workspace-root", required=True, help="Explicit workspace root directory.")
    parser.add_argument("--target", required=True, help="Relative target path inside the workspace root.")
    parser.add_argument("--payload", required=True, help="Text payload to write.")
    parser.add_argument("--force", action="store_true", help="Record caller force-create intent; does not expand scope.")
    parser.add_argument("--allow-replace", dest="allow_replace", action="store_true", default=True, help="Allow replacing an existing target file (default).")
    parser.add_argument("--no-allow-replace", dest="allow_replace", action="store_false", help="Block if the target already exists.")
    parser.add_argument("--rollback", action="store_true", help="After a successful write, perform exact-target rollback.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing.")
    parser.add_argument("--summary", action="store_true", help="Print compact summary instead of full records.")
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT, help="Deterministic timestamp for generated records.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = build_workspace_file_effect_request(
        request_id="workspace-file-effect-cli-request",
        workspace_root=args.workspace_root,
        relative_target_path=args.target,
        payload_text=args.payload,
        force_create=args.force,
        allow_replace=args.allow_replace,
        created_at=args.created_at,
    )
    validation = validate_workspace_file_effect_request(request)
    if args.dry_run:
        output = {
            "dry_run": True,
            "validation": {"ok": validation.ok, "findings": validation.findings},
            "summary": {
                "workspace_root": request.workspace_root,
                "relative_target_path": request.relative_target_path,
                "single_target_only": True,
                "would_write": validation.ok,
                "writes_performed": False,
                "network_performed": False,
                "provider_invocation_performed": False,
                "prompt_assembly_performed": False,
                "subprocess_performed": False,
                "shell_performed": False,
            },
        }
        print(_json(output if not args.summary else output["summary"]))
        return 0 if validation.ok else 2

    preimage, result = perform_workspace_file_effect(request, created_at=args.created_at)
    receipt = build_workspace_file_effect_receipt(request, preimage, result, created_at=args.created_at)
    postcondition = perform_workspace_file_postcondition_check(receipt, created_at=args.created_at)
    rollback_plan = build_workspace_file_rollback_plan(receipt, preimage, created_at=args.created_at)
    rollback_result = None
    rollback_receipt = None
    rollback_postcondition = None
    if args.rollback and receipt.real_effect_performed:
        rollback_result = perform_workspace_file_rollback(rollback_plan, created_at=args.created_at)
        rollback_receipt = build_workspace_file_rollback_receipt(rollback_plan, rollback_result, created_at=args.created_at)
        rollback_postcondition = perform_workspace_file_rollback_postcondition_check(rollback_plan, rollback_receipt, created_at=args.created_at)
    audit = build_workspace_file_production_audit_receipt(
        receipt,
        postcondition,
        rollback_plan,
        rollback_receipt=rollback_receipt,
        rollback_postcondition=rollback_postcondition,
        created_at=args.created_at,
    )
    if args.summary:
        output = {
            "effect": summarize_workspace_file_effect_result(result),
            "receipt": summarize_workspace_file_effect_receipt(receipt),
            "postcondition": summarize_workspace_file_postcondition_check(postcondition),
            "rollback": summarize_workspace_file_rollback_result(rollback_result) if rollback_result else None,
            "rollback_receipt": summarize_workspace_file_rollback_receipt(rollback_receipt) if rollback_receipt else None,
            "audit": summarize_workspace_file_production_audit_receipt(audit),
            "single_explicit_workspace_file_target_only": True,
            "general_filesystem_access_performed": False,
            "directory_cleanup_performed": False,
            "recursive_delete_performed": False,
            "wildcard_delete_performed": False,
            "unrelated_file_delete_performed": False,
            "network_performed": False,
            "provider_invocation_performed": False,
            "prompt_assembly_performed": False,
            "subprocess_performed": False,
            "shell_performed": False,
        }
    else:
        output = {
            "request": request.to_dict(),
            "preimage": preimage.to_dict(),
            "result": result.to_dict(),
            "receipt": receipt.to_dict(),
            "postcondition": postcondition.to_dict(),
            "rollback_plan": rollback_plan.to_dict(),
            "rollback_result": rollback_result.to_dict() if rollback_result else None,
            "rollback_receipt": rollback_receipt.to_dict() if rollback_receipt else None,
            "rollback_postcondition": rollback_postcondition.to_dict() if rollback_postcondition else None,
            "production_audit": audit.to_dict(),
        }
    print(_json(output))
    return 0 if receipt.real_effect_performed else 2


if __name__ == "__main__":
    raise SystemExit(main())
