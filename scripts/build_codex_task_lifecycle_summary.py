from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_task_lifecycle_summary import (
    CodexTaskLifecycleSummaryError,
    CodexTaskLifecycleSummaryRequest,
    build_task_lifecycle_summary,
    write_task_lifecycle_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a deterministic Codex task lifecycle summary artifact from existing landing evidence.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--intended-commit-title", required=True)
    parser.add_argument("--pre-commit-finalizer-json", required=True)
    parser.add_argument("--pr-metadata-finalizer-json", required=True)
    parser.add_argument("--matrix-json-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pr-metadata-guard-json")
    parser.add_argument("--task-id")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = build_task_lifecycle_summary(
            CodexTaskLifecycleSummaryRequest(
                title=args.title,
                intended_commit_title=args.intended_commit_title,
                pre_commit_finalizer_json=args.pre_commit_finalizer_json,
                pr_metadata_finalizer_json=args.pr_metadata_finalizer_json,
                matrix_json_path=args.matrix_json_path,
                output=args.output,
                pr_metadata_guard_json=args.pr_metadata_guard_json,
                task_id=args.task_id,
            )
        )
        write_task_lifecycle_summary(summary, args.output)
    except CodexTaskLifecycleSummaryError as exc:
        print(f"codex_task_lifecycle_summary_error: {exc}", file=sys.stderr)
        return 1
    if args.summary:
        print(json.dumps({"summary_id": summary["summary_id"], "overall_lifecycle_status": summary["overall_lifecycle_status"], "rerun_required": summary["rerun_required"], "rerun_reason": summary["rerun_reason"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
