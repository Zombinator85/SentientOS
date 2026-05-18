#!/usr/bin/env python3
"""Run bounded workspace change-set preflight and optional transaction execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.workspace_change_set_execution import (  # noqa: E402
    EXECUTION_MODES,
    WorkspaceChangeSetExecutionPolicy,
    run_workspace_change_set_execution_wing,
    summarize_workspace_change_set_execution_closure_report,
    summarize_workspace_change_set_execution_ledger,
    summarize_workspace_change_set_execution_receipt,
    summarize_workspace_change_set_execution_result,
    summarize_workspace_change_set_rollback_execution_result,
)
from sentientos.workspace_change_set_preflight import (  # noqa: E402
    CHANGE_OPERATIONS,
    WorkspaceChangeSetPolicy,
    build_workspace_change_set_manifest,
    build_workspace_change_set_preflight_report,
    build_workspace_change_set_rollback_plan,
    build_workspace_change_set_transaction_plan,
    build_workspace_change_target_declaration,
    preflight_workspace_change_target,
    run_workspace_change_set_preflight_wing,
)


def _parse_target(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("target must use PATH=PAYLOAD")
    path, payload = value.split("=", 1)
    if not path:
        raise argparse.ArgumentTypeError("target path is required")
    return path, payload


def _jsonify(value: object) -> object:
    if hasattr(value, "to_dict"):
        return cast(object, value.to_dict())
    if isinstance(value, tuple):
        return [_jsonify(item) for item in value]
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    return value


def _object_list(value: object) -> list[object]:
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return list(value)
    return []

def _summary_text(payload: dict[str, object]) -> str:
    if payload.get("dry_run"):
        preflight = cast(Mapping[str, Mapping[str, Mapping[str, object]]], payload["preflight"])
        summary = preflight["summary"]
        report = summary["preflight_report"]
        manifest = summary["manifest"]
        transaction = summary["transaction_plan"]
        return "\n".join([
            "SentientOS Workspace Change Set Transaction (dry-run)",
            f"manifest_status: {manifest['manifest_status']}",
            f"report_status: {report['report_status']}",
            f"transaction_plan_status: {transaction['transaction_plan_status']}",
            f"target_count: {manifest['target_count']}",
            "target_writes: false",
            "rollback_performed: false",
            "ledger_artifact_written: false",
        ])
    execution = cast(Mapping[str, object], payload["execution_summary"])
    receipt = cast(Mapping[str, object], payload["execution_receipt_summary"])
    rollback = cast(Mapping[str, object], payload["rollback_summary"])
    closure = cast(Mapping[str, object], payload["closure_summary"])
    ledger = cast(Mapping[str, object] | None, payload.get("ledger_summary"))
    artifact = cast(Mapping[str, object], payload.get("ledger_artifact") or {})
    return "\n".join([
        "SentientOS Workspace Change Set Transaction",
        f"execution_status: {execution['execution_status']}",
        f"receipt_status: {receipt['receipt_status']}",
        f"applied_target_ids: {_object_list(execution['applied_target_ids'])}",
        f"failed_target_ids: {_object_list(execution['failed_target_ids'])}",
        f"skipped_target_ids: {_object_list(execution['skipped_target_ids'])}",
        f"rollback_status: {rollback['rollback_status']}",
        f"rollback_target_order: {_object_list(rollback['rollback_target_order'])}",
        f"closure_status: {closure['closure_status']}",
        f"ledger_status: {ledger['lifecycle_status'] if ledger else 'not_requested'}",
        f"ledger_artifact_written: {bool(artifact.get('artifact_written'))}",
        "bounded_change_set_execution_only: true",
        "general_filesystem_access_performed: false",
        "cleanup_performed: false",
        "subprocess_shell_network_provider_prompt: false",
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--target", action="append", type=_parse_target, required=True, help="PATH=PAYLOAD; may be supplied multiple times")
    parser.add_argument("--operation", choices=sorted(CHANGE_OPERATIONS), default="create_file")
    parser.add_argument("--mode", choices=sorted(EXECUTION_MODES), default="change_set_execute_full_guarded")
    parser.add_argument("--ledger-output")
    rollback_group = parser.add_mutually_exclusive_group()
    rollback_group.add_argument("--rollback-on-failure", dest="rollback_on_failure", action="store_true", default=None)
    rollback_group.add_argument("--no-rollback-on-failure", dest="rollback_on_failure", action="store_false")
    parser.add_argument("--rollback-after-execute", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00")
    parser.add_argument("--max-targets", type=int, default=8)
    parser.add_argument("--max-payload-bytes", type=int, default=65536)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    targets = tuple(
        build_workspace_change_target_declaration(
            relative_target_path=path,
            operation=args.operation,
            payload_text=payload,
            allow_replace=True,
            allow_create=True,
            created_at=args.created_at,
        )
        for path, payload in args.target
    )
    preflight_policy = WorkspaceChangeSetPolicy(max_targets=args.max_targets, max_payload_bytes_per_target=args.max_payload_bytes)
    manifest = build_workspace_change_set_manifest(workspace_root=args.workspace_root, targets=targets, policy=preflight_policy, created_at=args.created_at)
    target_preflights = tuple(preflight_workspace_change_target(workspace_root=args.workspace_root, target=target, policy=preflight_policy, created_at=args.created_at) for target in targets)
    preflight_report = build_workspace_change_set_preflight_report(manifest=manifest, target_preflights=target_preflights, created_at=args.created_at)
    rollback_plan = build_workspace_change_set_rollback_plan(manifest=manifest, preflight_report=preflight_report, target_preflights=target_preflights, created_at=args.created_at)
    transaction_plan = build_workspace_change_set_transaction_plan(manifest=manifest, preflight_report=preflight_report, rollback_plan=rollback_plan, created_at=args.created_at)
    preflight = run_workspace_change_set_preflight_wing(workspace_root=args.workspace_root, targets=targets, policy=preflight_policy, created_at=args.created_at)
    if args.dry_run:
        payload = {
            "dry_run": True,
            "metadata_only": True,
            "preflight_planning_only": True,
            "target_write_performed": False,
            "rollback_performed": False,
            "ledger_artifact_written": False,
            "preflight": preflight,
        }
        print(_summary_text(payload) if args.summary else json.dumps(_jsonify(payload), indent=2, sort_keys=True))
        return 0 if preflight["preflight_report"]["report_status"] in {"workspace_change_set_preflight_passed", "workspace_change_set_preflight_passed_with_warnings"} else 2

    execution_policy = WorkspaceChangeSetExecutionPolicy(max_targets=args.max_targets)
    wing = run_workspace_change_set_execution_wing(
        manifest=manifest,
        preflight_report=preflight_report,
        rollback_plan=rollback_plan,
        transaction_plan=transaction_plan,
        execution_mode=args.mode,
        rollback_on_failure=args.rollback_on_failure,
        rollback_after_execute=args.rollback_after_execute,
        write_ledger=bool(args.ledger_output) or args.mode in {"change_set_execute_with_ledger", "change_set_execute_rollback_with_ledger", "change_set_execute_full_guarded"},
        ledger_output_path=args.ledger_output,
        policy=execution_policy,
        created_at=args.created_at,
    )
    artifact = None
    if args.ledger_output and wing.ledger is not None:
        # The wing writes the artifact; this records expected posture for CLI output.
        artifact = {"artifact_written": Path(args.ledger_output).exists(), "path": args.ledger_output}
    payload = {
        "dry_run": False,
        "request": wing.request,
        "execution_result": wing.execution_result,
        "execution_receipt": wing.execution_receipt,
        "rollback_result": wing.rollback_result,
        "rollback_receipt": wing.rollback_receipt,
        "ledger": wing.ledger,
        "closure_report": wing.closure_report,
        "ledger_artifact": artifact,
        "execution_summary": summarize_workspace_change_set_execution_result(wing.execution_result),
        "execution_receipt_summary": summarize_workspace_change_set_execution_receipt(wing.execution_receipt),
        "rollback_summary": summarize_workspace_change_set_rollback_execution_result(wing.rollback_result),
        "ledger_summary": summarize_workspace_change_set_execution_ledger(wing.ledger) if wing.ledger else None,
        "closure_summary": summarize_workspace_change_set_execution_closure_report(wing.closure_report),
    }
    print(_summary_text(payload) if args.summary else json.dumps(_jsonify(payload), indent=2, sort_keys=True))
    return 0 if wing.execution_result.execution_status in {"workspace_change_set_execution_performed", "workspace_change_set_execution_performed_with_warnings", "workspace_change_set_execution_partially_performed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
