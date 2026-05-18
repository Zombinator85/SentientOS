#!/usr/bin/env python3
"""Verify/replay-audit completed workspace change-set execution evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.workspace_change_set_execution_verification import (  # noqa: E402
    load_verification_evidence,
    summarize_workspace_change_set_execution_verification_result,
    verify_workspace_change_set_execution,
)


def _jsonify(value: object) -> object:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_jsonify(item) for item in value]
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    return value


def _summary_text(payload: dict[str, object]) -> str:
    summary = cast(Mapping[str, object], payload["verification_summary"])
    return "\n".join([
        "SentientOS Workspace Change Set Execution Verification / Replay Audit",
        f"verification_status: {summary['verification_status']}",
        f"target_count: {summary['target_count']}",
        f"postcondition_digest_agreement: {summary['postcondition_digest_agreement']}",
        f"rollback_digest_agreement: {summary['rollback_digest_agreement']}",
        f"partial_state_visible: {summary['partial_state_visible']}",
        f"unknown_target_ids: {list(cast(Iterable[object], summary['unknown_target_ids']))}",
        f"finding_codes: {list(cast(Iterable[object], summary['finding_codes']))}",
        "verification_only: true",
        "read_only_except_optional_audit_artifact: true",
        "execution_invoked: false",
        "rollback_invoked: false",
        "cleanup_performed: false",
        "subprocess_shell_network_provider_prompt: false",
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="JSON evidence containing manifest, preflight_report, rollback_plan, transaction_plan, execution result/receipt, and optional rollback/ledger/closure records")
    parser.add_argument("--audit-output", help="Optional explicit verification/audit artifact output path")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    evidence = load_verification_evidence(args.evidence)
    wing = verify_workspace_change_set_execution(**evidence, audit_output_path=args.audit_output, created_at=args.created_at)
    payload = {
        "request": wing.request,
        "verification_result": wing.verification_result,
        "verification_summary": summarize_workspace_change_set_execution_verification_result(wing.verification_result),
    }
    print(_summary_text(payload) if args.summary else json.dumps(_jsonify(payload), indent=2, sort_keys=True))
    return 0 if wing.verification_result.verification_status in {"verified_clean", "verified_with_partial_state", "verified_rolled_back"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
