#!/usr/bin/env python3
"""Preflight a bounded workspace change set without writing target files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.workspace_change_set_preflight import (
    CHANGE_OPERATIONS,
    WorkspaceChangeSetPolicy,
    build_default_workspace_change_set_policy,
    build_workspace_change_target_declaration,
    run_workspace_change_set_preflight_wing,
)


def _parse_target(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("target must use PATH=PAYLOAD")
    path, payload = value.split("=", 1)
    if not path:
        raise argparse.ArgumentTypeError("target path is required")
    return path, payload


def _output_path_is_safe(path_text: str) -> tuple[bool, str]:
    if not path_text or path_text.strip() == "":
        return False, "output path is required"
    path = Path(path_text).expanduser()
    if path.resolve(strict=False) == Path(path.anchor or "/").resolve(strict=False):
        return False, "output path may not be filesystem root"
    if path.exists() and path.is_dir():
        return False, "output path may not be a directory"
    if path.is_symlink():
        return False, "output path may not be a symlink"
    if not path.parent.exists():
        return False, "output parent directory must exist"
    return True, ""


def _summary_text(payload: dict[str, object]) -> str:
    summary = cast(Mapping[str, Mapping[str, object]], payload["summary"])
    report = summary["preflight_report"]
    manifest = summary["manifest"]
    rollback = summary["rollback_plan"]
    transaction = summary["transaction_plan"]
    return "\n".join(
        [
            "SentientOS Workspace Change Set Preflight",
            f"manifest_status: {manifest['manifest_status']}",
            f"report_status: {report['report_status']}",
            f"target_count: {manifest['target_count']}",
            f"passed_targets: {report['passed_targets']}",
            f"blocked_targets: {report['blocked_targets']}",
            f"rollback_plan_status: {rollback['rollback_plan_status']}",
            f"transaction_plan_status: {transaction['transaction_plan_status']}",
            "preflight/planning only: true",
            "reads only explicitly declared target metadata/digests: true",
            "target writes performed: false",
            "rollback performed: false",
            "runner/orchestrator invoked: false",
            f"digest: {transaction['digest']}",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only workspace change-set preflight/plan")
    parser.add_argument("--workspace-root", required=True, help="workspace root containing explicitly declared targets")
    parser.add_argument("--target", action="append", type=_parse_target, required=True, help="explicit target declaration as PATH=PAYLOAD; may be repeated")
    parser.add_argument("--operation", choices=sorted(CHANGE_OPERATIONS), default="create_file", help="operation for all supplied target declarations")
    parser.add_argument("--output", help="optional exact path for one preflight/plan JSON artifact")
    parser.add_argument("--summary", action="store_true", help="print compact preflight summary")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00", help="deterministic timestamp")
    parser.add_argument("--max-targets", type=int, help="override target count limit")
    parser.add_argument("--max-payload-bytes", type=int, help="override per-target payload byte limit")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    base_policy = build_default_workspace_change_set_policy()
    policy = WorkspaceChangeSetPolicy(
        max_targets=args.max_targets if args.max_targets is not None else base_policy.max_targets,
        max_payload_bytes_per_target=args.max_payload_bytes if args.max_payload_bytes is not None else base_policy.max_payload_bytes_per_target,
        max_total_payload_bytes=base_policy.max_total_payload_bytes,
        require_parent_exists=base_policy.require_parent_exists,
        allow_replace=base_policy.allow_replace,
        allow_create=base_policy.allow_create,
        reject_symlink_targets=base_policy.reject_symlink_targets,
        reject_directory_targets=base_policy.reject_directory_targets,
        reject_wildcard_targets=base_policy.reject_wildcard_targets,
        read_existing_target_digest=base_policy.read_existing_target_digest,
        mutation_allowed=False,
    )
    try:
        declarations = tuple(
            build_workspace_change_target_declaration(
                relative_target_path=target_path,
                operation=args.operation,
                payload_text=payload,
                allow_replace=policy.allow_replace,
                allow_create=policy.allow_create,
                created_at=args.created_at,
            )
            for target_path, payload in args.target
        )
        payload = run_workspace_change_set_preflight_wing(
            workspace_root=args.workspace_root,
            targets=declarations,
            policy=policy,
            created_at=args.created_at,
        )
        output_text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True, default=str) + "\n"
        if args.output:
            safe, reason = _output_path_is_safe(args.output)
            if not safe:
                print(f"unsafe output path: {reason}", file=sys.stderr)
                return 2
            Path(args.output).expanduser().write_text(output_text, encoding="utf-8")
        if args.summary:
            print(_summary_text(payload), end="")
        else:
            print(output_text, end="")
        report = payload["preflight_report"]
        if isinstance(report, dict) and report.get("report_status") in {"workspace_change_set_preflight_blocked", "workspace_change_set_preflight_incomplete", "workspace_change_set_preflight_contradicted"}:
            return 2
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(f"workspace change set preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
