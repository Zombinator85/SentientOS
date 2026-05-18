#!/usr/bin/env python3
"""Review proposed workspace change-set metadata for admission only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.workspace_change_set_admission import (  # noqa: E402
    WorkspaceChangeSetAdmissionPolicy,
    build_workspace_change_set_admission_artifact,
    run_workspace_change_set_admission_wing,
    summarize_workspace_change_set_admission_decision,
)


def _summary_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    return "\n".join([
        "SentientOS Workspace Change Set Admission",
        f"admission_status: {summary['admission_status']}",
        f"proposed_target_count: {summary['proposed_target_count']}",
        f"declared_target_count: {summary['declared_target_count']}",
        f"operation_types: {list(summary['proposed_operation_types'])}",
        f"blocker_codes: {list(summary['blocker_codes'])}",
        f"warning_codes: {list(summary['warning_codes'])}",
        f"forbidden_authority_findings: {list(summary['forbidden_authority_findings'])}",
        f"preflight_may_be_attempted_next: {summary['preflight_may_be_attempted_next']}",
        "metadata_only: true",
        "non_authorizing: true",
        "preflight_performed: false",
        "execution_performed: false",
        "rollback_performed: false",
        "cleanup_performed: false",
        f"digest: {summary['digest']}",
        "",
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only workspace change-set admission decision")
    parser.add_argument("--proposal", required=True, help="proposal JSON containing metadata only")
    parser.add_argument("--output", help="optional exact path for one admission JSON artifact")
    parser.add_argument("--summary", action="store_true", help="print compact admission summary")
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
        proposal = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
        if not isinstance(proposal, dict):
            print("proposal JSON must be an object", file=sys.stderr)
            return 2
        policy = WorkspaceChangeSetAdmissionPolicy(max_targets=args.max_targets, max_payload_bytes_per_target=args.max_payload_bytes)
        wing = run_workspace_change_set_admission_wing(proposal, policy=policy, artifact_output_path=args.output, created_at=args.created_at)
        artifact = build_workspace_change_set_admission_artifact(wing)
        payload = {**artifact, "summary": summarize_workspace_change_set_admission_decision(wing.decision)}
        print(_summary_text(payload) if args.summary else json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True, default=str) + "", end="")
        if args.summary:
            return 0 if wing.decision.preflight_may_be_attempted_next else 2
        print()
        return 0 if wing.decision.preflight_may_be_attempted_next else 2
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"workspace change set admission failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
