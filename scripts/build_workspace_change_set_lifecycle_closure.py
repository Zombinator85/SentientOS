#!/usr/bin/env python3
"""Build a metadata-only lifecycle closure manifest from supplied evidence JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.workspace_change_set_lifecycle_closure import (  # noqa: E402
    build_workspace_change_set_lifecycle_closure_manifest,
    load_lifecycle_closure_evidence,
    summarize_workspace_change_set_lifecycle_closure_manifest,
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
    summary = cast(Mapping[str, object], payload["closure_summary"])
    return "\n".join([
        "SentientOS Workspace Change Set Lifecycle Closure Manifest",
        f"lifecycle_closure_status: {summary['lifecycle_closure_status']}",
        f"verification_status: {summary['verification_status']}",
        f"declared_target_count: {summary['declared_target_count']}",
        f"applied_target_count: {summary['applied_target_count']}",
        f"failed_target_count: {summary['failed_target_count']}",
        f"skipped_target_count: {summary['skipped_target_count']}",
        f"rolled_back_target_count: {summary['rolled_back_target_count']}",
        f"open_target_count: {summary['open_target_count']}",
        f"contradiction_codes: {list(cast(Iterable[object], summary['contradiction_codes']))}",
        f"blocker_codes: {list(cast(Iterable[object], summary['blocker_codes']))}",
        "metadata_only: true",
        "target_file_read_performed: false",
        "execution_invoked: false",
        "rollback_invoked: false",
        "verification_replay_invoked: false",
        "cleanup_performed: false",
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="JSON evidence containing existing preflight, execution, optional rollback/ledger/closure, and verification result records")
    parser.add_argument("--output", help="Optional explicit lifecycle closure manifest artifact output path")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    evidence = load_lifecycle_closure_evidence(args.evidence)
    wing = build_workspace_change_set_lifecycle_closure_manifest(**evidence, artifact_output_path=args.output, created_at=args.created_at)
    payload = {
        "request": wing.request,
        "closure_manifest": wing.closure_manifest,
        "closure_result": wing.closure_result,
        "closure_summary": summarize_workspace_change_set_lifecycle_closure_manifest(wing.closure_manifest),
    }
    print(_summary_text(payload) if args.summary else json.dumps(_jsonify(payload), indent=2, sort_keys=True))
    return 0 if wing.closure_manifest.lifecycle_closure_status in {"lifecycle_closed_clean", "lifecycle_closed_with_partial_state", "lifecycle_closed_after_rollback", "lifecycle_open", "lifecycle_insufficient_evidence"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
