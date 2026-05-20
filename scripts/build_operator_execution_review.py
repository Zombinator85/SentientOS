from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, cast
from sentientos.work_item_execution_review import OperatorExecutionReviewPolicy, OperatorExecutionReviewRequest, evaluate_operator_execution_review, write_operator_execution_review_packet

def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Build operator execution review packet')
    ap.add_argument('--preflight-run', required=True, type=Path); ap.add_argument('--proposal', required=True, type=Path)
    ap.add_argument('--admission-run', type=Path); ap.add_argument('--operator-review', type=Path); ap.add_argument('--promotion-dossier', type=Path); ap.add_argument('--matrix-report', type=Path)
    ap.add_argument('--output', type=Path); ap.add_argument('--summary', action='store_true'); ap.add_argument('--require-matrix', action='store_true'); ap.add_argument('--require-artifacts', action='store_true')
    ap.add_argument('--allow-warning-preflight', dest='allow_warning_preflight', action='store_true', default=False); ap.add_argument('--no-allow-warning-preflight', dest='allow_warning_preflight', action='store_false')
    ap.add_argument('--review-only', action='store_true')
    args = ap.parse_args(argv)
    res = evaluate_operator_execution_review(OperatorExecutionReviewRequest(preflight_run_packet=_load(args.preflight_run) or {}, proposal=_load(args.proposal), admission_run_packet=_load(args.admission_run), operator_review_packet=_load(args.operator_review), promotion_dossier=_load(args.promotion_dossier), matrix_report=_load(args.matrix_report)), policy=OperatorExecutionReviewPolicy(allow_warning_preflight=args.allow_warning_preflight, matrix_required=args.require_matrix, artifacts_required=args.require_artifacts, review_only=args.review_only))
    if args.output is not None: write_operator_execution_review_packet(res, args.output)
    if args.summary or args.output is None:
        p = res.packet
        print(json.dumps({"status":res.status,"work_item_id":p.work_item_id,"transaction_plan_ready":p.transaction_plan_ready,"digest":p.execution_review_packet_digest}, indent=2, sort_keys=True))
    return 0 if res.status in {'execution_review_ready','execution_review_ready_with_warnings','execution_review_manual_review_required'} else 2

if __name__ == '__main__':
    raise SystemExit(main())
