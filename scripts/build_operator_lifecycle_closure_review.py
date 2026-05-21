from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, cast
from sentientos.work_item_lifecycle_closure_review import (
    OperatorLifecycleClosureReviewPolicy,
    OperatorLifecycleClosureReviewRequest,
    evaluate_operator_lifecycle_closure_review,
    write_operator_lifecycle_closure_review_packet,
)

def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Build operator lifecycle closure review packet')
    ap.add_argument('--verification-run', required=True, type=Path); ap.add_argument('--proposal', required=True, type=Path)
    ap.add_argument('--execution-run', type=Path); ap.add_argument('--preflight-run', type=Path); ap.add_argument('--matrix-report', type=Path)
    ap.add_argument('--output', type=Path); ap.add_argument('--summary', action='store_true'); ap.add_argument('--require-matrix', action='store_true'); ap.add_argument('--require-artifacts', action='store_true')
    ap.add_argument('--allow-warning-verification', dest='allow_warning_verification', action='store_true', default=False); ap.add_argument('--no-allow-warning-verification', dest='allow_warning_verification', action='store_false')
    args = ap.parse_args(argv)
    res = evaluate_operator_lifecycle_closure_review(
        OperatorLifecycleClosureReviewRequest(
            verification_run_packet=_load(args.verification_run) or {}, proposal=_load(args.proposal),
            execution_run_packet=_load(args.execution_run), preflight_run_packet=_load(args.preflight_run), matrix_report=_load(args.matrix_report)
        ),
        policy=OperatorLifecycleClosureReviewPolicy(allow_warning_verification=args.allow_warning_verification, matrix_required=args.require_matrix, artifacts_required=args.require_artifacts),
    )
    if args.output is not None: write_operator_lifecycle_closure_review_packet(res, args.output)
    if args.summary or args.output is None:
        p = res.packet
        print(json.dumps({"status":res.status,"work_item_id":p.work_item_id,"verification_run_status":p.verification_run_status,"digest":p.closure_review_packet_digest}, indent=2, sort_keys=True))
    return 0 if res.status in {'closure_review_ready','closure_review_ready_with_warnings','closure_review_manual_review_required'} else 2

if __name__ == '__main__':
    raise SystemExit(main())
