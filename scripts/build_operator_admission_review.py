from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, cast
from sentientos.work_item_operator_admission_review import (
    OperatorAdmissionReviewPolicy, OperatorAdmissionReviewRequest, evaluate_operator_admission_review, write_operator_admission_review_packet,
)

def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Build metadata-only operator admission review packet from promotion dossier')
    ap.add_argument('--promotion-dossier', required=True, type=Path)
    ap.add_argument('--review-packet', type=Path)
    ap.add_argument('--work-item-packet', type=Path)
    ap.add_argument('--matrix-report', type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--summary', action='store_true')
    ap.add_argument('--require-matrix', action='store_true')
    ap.add_argument('--require-artifacts', action='store_true')
    ap.add_argument('--allow-warning-review', dest='allow_warning_review', action='store_true', default=True)
    ap.add_argument('--no-allow-warning-review', dest='allow_warning_review', action='store_false')
    args = ap.parse_args(argv)
    result = evaluate_operator_admission_review(
        OperatorAdmissionReviewRequest(
            promotion_dossier=_load(args.promotion_dossier) or {}, review_packet=_load(args.review_packet), work_item_packet=_load(args.work_item_packet), matrix_report=_load(args.matrix_report)
        ),
        policy=OperatorAdmissionReviewPolicy(allow_warning_review=args.allow_warning_review, matrix_required=args.require_matrix, artifacts_required=args.require_artifacts),
    )
    if args.output is not None:
        write_operator_admission_review_packet(result, args.output)
    if args.summary or args.output is None:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status in {'admission_review_ready','admission_review_ready_with_warnings','admission_review_manual_review_required','admission_review_requires_clarification'} else 2

if __name__ == '__main__':
    raise SystemExit(main())
