from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.work_item_promotion_gate import WorkItemPromotionPolicy, WorkItemPromotionRequest, evaluate_work_item_promotion, write_work_item_promotion_dossier


def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _exit(status: str) -> int:
    if status in {
        "promotion_blocked_authority",
        "promotion_contradicted",
        "promotion_insufficient_evidence",
        "promotion_failed",
    }:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate dry-run review packet promotion readiness")
    parser.add_argument("--review-packet", required=True, type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--handoff", type=Path)
    parser.add_argument("--dry-run-result", type=Path)
    parser.add_argument("--dry-run-closure", type=Path)
    parser.add_argument("--matrix-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--require-matrix", action="store_true")
    parser.add_argument("--allow-warning-promotion", dest="allow_warning_promotion", action="store_true", default=True)
    parser.add_argument("--no-allow-warning-promotion", dest="allow_warning_promotion", action="store_false")
    args = parser.parse_args(argv)

    result = evaluate_work_item_promotion(
        WorkItemPromotionRequest(
            review_packet=_load(args.review_packet) or {},
            packet=_load(args.packet),
            handoff=_load(args.handoff),
            dry_run_result=_load(args.dry_run_result),
            dry_run_closure=_load(args.dry_run_closure),
            matrix_report=_load(args.matrix_report),
        ),
        policy=WorkItemPromotionPolicy(allow_warning_promotion=args.allow_warning_promotion, matrix_required=args.require_matrix),
    )
    payload = result.to_dict()
    if args.output is not None:
        write_work_item_promotion_dossier(result, args.output)
    if args.summary or args.output is None:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return _exit(result.decision.status)


if __name__ == "__main__":
    raise SystemExit(main())
