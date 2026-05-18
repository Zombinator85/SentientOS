#!/usr/bin/env python3
"""Run explicit bounded workspace change-set lifecycle orchestration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.workspace_change_set_lifecycle_orchestrator import (  # noqa: E402
    LIFECYCLE_MODES,
    WorkspaceChangeSetLifecycleOrchestrationPolicy,
    run_workspace_change_set_lifecycle_orchestration,
    summarize_workspace_change_set_lifecycle_orchestration_result,
)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "_asdict"):
        return {key: _jsonable(item) for key, item in value._asdict().items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _summary_text(summary: dict[str, Any]) -> str:
    return "\n".join([
        "SentientOS Workspace Change Set Lifecycle Orchestration",
        f"requested_mode: {summary['requested_mode']}",
        f"stages_requested: {list(summary['stages_requested'])}",
        f"stages_attempted: {list(summary['stages_attempted'])}",
        f"stages_skipped: {list(summary['stages_skipped'])}",
        f"stop_reason: {summary['stop_reason']}",
        f"admission_status: {summary['admission_status']}",
        f"preflight_status: {summary['preflight_status']}",
        f"transaction_plan_status: {summary['transaction_plan_status']}",
        f"transaction_plan_ready: {summary['transaction_plan_ready']}",
        f"execution_status: {summary['execution_status']}",
        f"verification_status: {summary['verification_status']}",
        f"final_lifecycle_status: {summary['final_lifecycle_status']}",
        f"partial_state_visible: {summary['partial_state_visible']}",
        f"artifact_records: {list(summary['artifact_records'])}",
        f"dry_run: {summary['dry_run']}",
        "target_write_performed_by_orchestrator: false",
        "target_file_read_performed_by_orchestrator: false",
        "target_digest_recomputed_by_orchestrator: false",
        "cleanup_performed: false",
        "external_tool_invoked: false",
        f"digest: {summary['digest']}",
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", required=True, help="workspace change-set proposal JSON")
    parser.add_argument("--workspace-root", help="required for modes that include preflight or later stages")
    parser.add_argument("--mode", choices=sorted(LIFECYCLE_MODES), required=True)
    parser.add_argument("--summary", action="store_true", help="print compact lifecycle summary")
    parser.add_argument("--admission-output")
    parser.add_argument("--preflight-output")
    parser.add_argument("--execution-output")
    parser.add_argument("--verification-output")
    parser.add_argument("--closure-output")
    parser.add_argument("--orchestration-output")
    parser.add_argument("--dry-run", action="store_true", help="alias for --mode dry_run_full_lifecycle; never executes targets")
    rollback_group = parser.add_mutually_exclusive_group()
    rollback_group.add_argument("--rollback-on-failure", dest="rollback_on_failure", action="store_true", default=None)
    rollback_group.add_argument("--no-rollback-on-failure", dest="rollback_on_failure", action="store_false")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00")
    parser.add_argument("--max-targets", type=int, default=8)
    parser.add_argument("--max-payload-bytes", type=int, default=65536)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    try:
        mode = "dry_run_full_lifecycle" if args.dry_run else args.mode
        proposal = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
        if not isinstance(proposal, dict):
            print("proposal JSON must be an object", file=sys.stderr)
            return 2
        policy = WorkspaceChangeSetLifecycleOrchestrationPolicy(max_targets=args.max_targets, max_payload_bytes_per_target=args.max_payload_bytes)
        wing = run_workspace_change_set_lifecycle_orchestration(
            proposal,
            mode=mode,
            workspace_root=args.workspace_root,
            policy=policy,
            admission_artifact_output_path=args.admission_output,
            preflight_artifact_output_path=args.preflight_output,
            execution_artifact_output_path=args.execution_output,
            verification_artifact_output_path=args.verification_output,
            closure_artifact_output_path=args.closure_output,
            orchestration_artifact_output_path=args.orchestration_output,
            rollback_on_failure=args.rollback_on_failure,
            created_at=args.created_at,
        )
        summary = summarize_workspace_change_set_lifecycle_orchestration_result(wing.result)
        print(_summary_text(summary) if args.summary else json.dumps(_jsonable({"request": wing.request, "result": wing.result, "summary": summary}), indent=2, sort_keys=True))
        return 0 if wing.result.stop_reason == "lifecycle_completed_for_requested_mode" else 2
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"workspace change set lifecycle orchestration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
