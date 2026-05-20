from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, cast
from sentientos.work_item_preflight_run import OperatorConfirmedPreflightPolicy, OperatorConfirmedPreflightRequest, evaluate_operator_confirmed_preflight, write_operator_confirmed_preflight_packet

def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Run operator-confirmed workspace preflight bridge')
    ap.add_argument('--admission-run', required=True, type=Path); ap.add_argument('--proposal', required=True, type=Path); ap.add_argument('--workspace-root', required=True)
    ap.add_argument('--operator-review', type=Path); ap.add_argument('--promotion-dossier', type=Path); ap.add_argument('--matrix-report', type=Path); ap.add_argument('--output', type=Path)
    ap.add_argument('--summary', action='store_true'); ap.add_argument('--require-matrix', action='store_true')
    ap.add_argument('--allow-warning-admission', dest='allow_warning_admission', action='store_true', default=False); ap.add_argument('--no-allow-warning-admission', dest='allow_warning_admission', action='store_false')
    ap.add_argument('--review-only', action='store_true')
    args = ap.parse_args(argv)
    res = evaluate_operator_confirmed_preflight(OperatorConfirmedPreflightRequest(admission_run_packet=_load(args.admission_run) or {}, proposal=_load(args.proposal), workspace_root=args.workspace_root, operator_review_packet=_load(args.operator_review), promotion_dossier=_load(args.promotion_dossier), matrix_report=_load(args.matrix_report)), policy=OperatorConfirmedPreflightPolicy(allow_warning_admission=args.allow_warning_admission, matrix_required=args.require_matrix, review_only=args.review_only))
    if args.output is not None: write_operator_confirmed_preflight_packet(res, args.output)
    if args.summary or args.output is None:
        pkt = res.packet
        print(json.dumps({"status": res.status, "work_item_id": pkt.work_item_id, "preflight_status": pkt.workspace_change_set_preflight_status, "transaction_plan_ready": pkt.transaction_plan_ready, "digest": pkt.preflight_run_packet_digest}, indent=2, sort_keys=True))
    return 0 if res.status in {'preflight_run_ready','preflight_run_ready_with_warnings'} else 2

if __name__ == '__main__':
    raise SystemExit(main())
