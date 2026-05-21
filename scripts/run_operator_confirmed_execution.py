from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, cast
from sentientos.work_item_execution_run import (
    OperatorConfirmedExecutionPolicy, OperatorConfirmedExecutionRequest,
    evaluate_operator_confirmed_execution, write_operator_confirmed_execution_packet,
)

def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None: return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Run operator confirmed workspace execution run')
    ap.add_argument('--execution-review', required=True, type=Path)
    ap.add_argument('--proposal', required=True, type=Path)
    ap.add_argument('--workspace-root', required=True)
    ap.add_argument('--confirm-execution', action='store_true')
    ap.add_argument('--preflight-run', type=Path)
    ap.add_argument('--admission-run', type=Path)
    ap.add_argument('--matrix-report', type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--summary', action='store_true')
    ap.add_argument('--require-matrix', action='store_true')
    ap.add_argument('--require-artifacts', action='store_true')
    ap.add_argument('--allow-warning-review', dest='allow_warning_review', action='store_true', default=False)
    ap.add_argument('--no-allow-warning-review', dest='allow_warning_review', action='store_false')
    ap.add_argument('--review-only', action='store_true')
    args = ap.parse_args(argv)
    res = evaluate_operator_confirmed_execution(OperatorConfirmedExecutionRequest(
        execution_review_packet=_load(args.execution_review) or {}, proposal=_load(args.proposal), workspace_root=args.workspace_root,
        operator_confirmation=bool(args.confirm_execution), preflight_run_packet=_load(args.preflight_run), admission_run_packet=_load(args.admission_run), matrix_report=_load(args.matrix_report)
    ), policy=OperatorConfirmedExecutionPolicy(allow_warning_review=args.allow_warning_review, matrix_required=args.require_matrix, artifacts_required=args.require_artifacts, review_only=args.review_only))
    if args.output is not None: write_operator_confirmed_execution_packet(res, args.output)
    if args.summary or args.output is None:
        p = res.packet
        print(json.dumps({"status": res.status, "work_item_id": p.work_item_id, "execution_status": p.workspace_change_set_execution_status, "digest": p.execution_run_packet_digest}, indent=2, sort_keys=True))
    return 0 if res.status in {"execution_run_completed", "execution_run_completed_with_warnings"} or (args.review_only and not res.packet.execution_wing_invoked) else 2

if __name__ == '__main__':
    raise SystemExit(main())
