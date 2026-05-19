from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.work_item_review_packet import WorkItemDryRunReviewRequest, build_work_item_dry_run_review_packet


def _exit_code(action: str) -> int:
    if action in {"contradicted_evidence", "blocked_authority_request", "insufficient_evidence", "failed_review_generation"}:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build metadata-only work-item dry-run review packet")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--mode", choices=("review_only", "review_with_dry_run", "review_with_dry_run_closure"), default="review_with_dry_run_closure")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--intake-output", type=Path)
    parser.add_argument("--handoff-output", type=Path)
    parser.add_argument("--dry-run-output", type=Path)
    parser.add_argument("--closure-output", type=Path)
    parser.add_argument("--review-output", type=Path)
    args = parser.parse_args(argv)

    payload: dict[str, Any] = json.loads(args.input.read_text(encoding="utf-8"))
    result = build_work_item_dry_run_review_packet(
        WorkItemDryRunReviewRequest(
            work_item_payload=payload,
            workspace_root=args.workspace_root,
            mode=args.mode,
            intake_output_path=str(args.intake_output) if args.intake_output else None,
            handoff_output_path=str(args.handoff_output) if args.handoff_output else None,
            dry_run_output_path=str(args.dry_run_output) if args.dry_run_output else None,
            closure_output_path=str(args.closure_output) if args.closure_output else None,
            review_output_path=str(args.review_output) if args.review_output else None,
        )
    )
    out = result.to_dict()
    if args.summary or not args.review_output:
        print(json.dumps(out, indent=2, sort_keys=True))
    if args.review_output:
        args.review_output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _exit_code(result.packet.operator_action)


if __name__ == "__main__":
    raise SystemExit(main())
