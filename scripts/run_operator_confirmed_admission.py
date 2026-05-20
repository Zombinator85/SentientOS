from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, cast
from sentientos.work_item_admission_run import (
    OperatorConfirmedAdmissionPolicy, OperatorConfirmedAdmissionRequest, evaluate_operator_confirmed_admission, write_operator_confirmed_admission_packet,
)

def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Run operator-confirmed workspace change-set admission bridge')
    ap.add_argument('--operator-review', required=True, type=Path)
    ap.add_argument('--proposal', required=True, type=Path)
    ap.add_argument('--promotion-dossier', type=Path)
    ap.add_argument('--review-packet', type=Path)
    ap.add_argument('--matrix-report', type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--summary', action='store_true')
    ap.add_argument('--require-matrix', action='store_true')
    ap.add_argument('--allow-warning-review', dest='allow_warning_review', action='store_true', default=False)
    ap.add_argument('--no-allow-warning-review', dest='allow_warning_review', action='store_false')
    ap.add_argument('--dry-run-review-only', action='store_true')
    args = ap.parse_args(argv)
    res = evaluate_operator_confirmed_admission(
        OperatorConfirmedAdmissionRequest(
            operator_review_packet=_load(args.operator_review) or {}, proposal=_load(args.proposal), promotion_dossier=_load(args.promotion_dossier), review_packet=_load(args.review_packet), matrix_report=_load(args.matrix_report)
        ), policy=OperatorConfirmedAdmissionPolicy(allow_warning_review=args.allow_warning_review, matrix_required=args.require_matrix, dry_run_review_only=args.dry_run_review_only)
    )
    if args.output is not None:
        write_operator_confirmed_admission_packet(res, args.output)
    if args.summary or args.output is None:
        pkt = res.packet
        print(json.dumps({"status": res.status, "work_item_id": pkt.work_item_id, "admission_status": pkt.workspace_change_set_admission_status, "digest": pkt.admission_run_packet_digest}, indent=2, sort_keys=True))
    return 0 if res.status in {'admission_run_accepted','admission_run_accepted_with_warnings'} else 2

if __name__ == '__main__':
    raise SystemExit(main())
