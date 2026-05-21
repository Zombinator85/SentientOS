from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, cast
from sentientos.work_item_verification_run import (
    OperatorConfirmedVerificationPolicy, OperatorConfirmedVerificationRequest,
    evaluate_operator_confirmed_verification, write_operator_confirmed_verification_packet,
)

def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None: return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Run operator confirmed workspace verification run')
    ap.add_argument('--execution-run', required=True, type=Path)
    ap.add_argument('--proposal', required=True, type=Path)
    ap.add_argument('--workspace-root', required=True)
    ap.add_argument('--confirm-verification', action='store_true')
    ap.add_argument('--execution-review', type=Path)
    ap.add_argument('--preflight-run', type=Path)
    ap.add_argument('--matrix-report', type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--summary', action='store_true')
    ap.add_argument('--require-matrix', action='store_true')
    ap.add_argument('--require-artifacts', action='store_true')
    ap.add_argument('--allow-warning-execution', dest='allow_warning_execution', action='store_true', default=False)
    ap.add_argument('--no-allow-warning-execution', dest='allow_warning_execution', action='store_false')
    ap.add_argument('--review-only', action='store_true')
    args = ap.parse_args(argv)
    res = evaluate_operator_confirmed_verification(OperatorConfirmedVerificationRequest(
        execution_run_packet=_load(args.execution_run) or {}, proposal=_load(args.proposal), workspace_root=args.workspace_root,
        operator_confirmation=bool(args.confirm_verification), execution_review_packet=_load(args.execution_review), preflight_run_packet=_load(args.preflight_run), matrix_report=_load(args.matrix_report)
    ), policy=OperatorConfirmedVerificationPolicy(allow_warning_execution=args.allow_warning_execution, matrix_required=args.require_matrix, artifacts_required=args.require_artifacts, review_only=args.review_only))
    if args.output is not None: write_operator_confirmed_verification_packet(res, args.output)
    if args.summary or args.output is None:
        p = res.packet
        print(json.dumps({"status": res.status, "work_item_id": p.work_item_id, "verification_status": p.workspace_change_set_verification_status, "digest": p.verification_run_packet_digest}, indent=2, sort_keys=True))
    return 0 if res.status in {"verification_run_passed", "verification_run_passed_with_warnings"} or (args.review_only and not res.packet.verification_wing_invoked) else 2

if __name__ == '__main__':
    raise SystemExit(main())
