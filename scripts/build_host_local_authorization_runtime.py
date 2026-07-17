#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
from sentientos.host_local_authorization_runtime import *  # noqa: F403
from sentientos.local_authorization_grant import build_local_authorization_grant_expiry_evaluation, verify_local_authorization_grant, validate_local_authorization_grant_ledger

def _load(p: str) -> dict[str, Any]: return dict(json.loads(Path(p).read_text()))
def _write(obj: Any, out: str|None) -> None:
    payload = obj.to_dict() if hasattr(obj, 'to_dict') else obj
    text=json.dumps(payload, sort_keys=True, indent=2)
    if out: Path(out).write_text(text, encoding='utf-8')
    else: print(text)

def _request(d: dict[str, Any]) -> HostLocalAuthorizationReviewRequest: return HostLocalAuthorizationReviewRequest(**d)
def _op(d: dict[str, Any]) -> OperatorLocalAuthorizationDecision: return OperatorLocalAuthorizationDecision(**d)
def _pol(d: dict[str, Any]) -> PolicyLocalAuthorizationDecision: return PolicyLocalAuthorizationDecision(**d)
def _plan(d: dict[str, Any]) -> HostLocalAuthorizationIssuePlan: return HostLocalAuthorizationIssuePlan(**d)

def main(argv: list[str]|None=None) -> int:
    ap=argparse.ArgumentParser(description='Build/validate explicit host local authorization custody metadata; no fulfillment or host effects.')
    sub=ap.add_subparsers(dest='cmd', required=True)
    for c in ['validate-review-request','validate-decision','validate-plan','validate-ledger','summarize','render-json','render-markdown','inspect']:
        p=sub.add_parser(c); p.add_argument('input'); p.add_argument('--output')
    p=sub.add_parser('decide-operator'); p.add_argument('--request', required=True); p.add_argument('--identity', required=True); p.add_argument('--role', required=True); p.add_argument('--disposition', default='approve'); p.add_argument('--reason-code', action='append', default=['explicit_operator_decision']); p.add_argument('--note', default=''); p.add_argument('--output')
    p=sub.add_parser('decide-policy'); p.add_argument('--request', required=True); p.add_argument('--identity', required=True); p.add_argument('--policy-version', required=True); p.add_argument('--disposition', default='approve'); p.add_argument('--reason-code', action='append', default=['explicit_policy_decision']); p.add_argument('--note', default=''); p.add_argument('--output')
    p=sub.add_parser('plan-issue'); p.add_argument('--request', required=True); p.add_argument('--operator-decision', required=True); p.add_argument('--policy-decision', required=True); p.add_argument('--prior-ledger-digest', default='sha256:empty'); p.add_argument('--idempotency-key'); p.add_argument('--output')
    p=sub.add_parser('issue'); p.add_argument('--request', required=True); p.add_argument('--operator-decision', required=True); p.add_argument('--policy-decision', required=True); p.add_argument('--plan', required=True); p.add_argument('--runtime-state-root'); p.add_argument('--apply', action='store_true'); p.add_argument('--output')
    p=sub.add_parser('evaluate-expiry'); p.add_argument('--grant', required=True); p.add_argument('--now', required=True); p.add_argument('--output')
    p=sub.add_parser('verify-grant'); p.add_argument('--grant', required=True); p.add_argument('--output')
    p=sub.add_parser('revoke'); p.add_argument('--grant', required=True); p.add_argument('--ledger', required=True); p.add_argument('--identity', required=True); p.add_argument('--reason-code', action='append', default=['explicit_revocation']); p.add_argument('--apply', action='store_true'); p.add_argument('--output')
    p=sub.add_parser('diff'); p.add_argument('left'); p.add_argument('right')
    p=sub.add_parser('build-review-request'); p.add_argument('--evaluation', required=True); p.add_argument('--target-label', action='append', required=True); p.add_argument('--not-before', required=True); p.add_argument('--not-after', required=True); p.add_argument('--expiry', required=True); p.add_argument('--output')
    args=ap.parse_args(argv)
    try:
        if args.cmd=='validate-review-request': _write(validate_review_request(_load(args.input)), args.output); return 0 if validate_review_request(_load(args.input)).ok else 64
        if args.cmd=='validate-decision': _write(validate_decision(_load(args.input)), args.output); return 0 if validate_decision(_load(args.input)).ok else 64
        if args.cmd=='validate-plan': _write(validate_plan(_load(args.input)), args.output); return 0 if validate_plan(_load(args.input)).ok else 64
        if args.cmd in {'summarize','inspect','render-json'}: _write(dashboard_projection(world_state_records(snapshot=HostLocalAuthorizationLedgerSnapshot(**_load(args.input))) if 'schema_version' in _load(args.input) else []), args.output); return 0
        if args.cmd=='render-markdown':
            text=render_markdown(_load(args.input)); Path(args.output).write_text(text) if args.output else print(text); return 0
        if args.cmd=='decide-operator': _write(build_operator_decision(_request(_load(args.request)), identity=args.identity, role_or_policy_version=args.role, disposition=args.disposition, reason_codes=args.reason_code, note=args.note), args.output); return 0
        if args.cmd=='decide-policy': _write(build_policy_decision(_request(_load(args.request)), identity=args.identity, role_or_policy_version=args.policy_version, disposition=args.disposition, reason_codes=args.reason_code, note=args.note), args.output); return 0
        if args.cmd=='plan-issue': _write(build_issue_plan(_request(_load(args.request)), _op(_load(args.operator_decision)), _pol(_load(args.policy_decision)), prior_ledger_digest=args.prior_ledger_digest, idempotency_key=args.idempotency_key), args.output); return 0
        if args.cmd=='issue': _write(HostLocalAuthorizationRuntimeCoordinator(runtime_state_root=args.runtime_state_root).issue(_request(_load(args.request)), _op(_load(args.operator_decision)), _pol(_load(args.policy_decision)), _plan(_load(args.plan)), apply=args.apply), args.output); return 0
        if args.cmd=='evaluate-expiry': _write(build_local_authorization_grant_expiry_evaluation(_load(args.grant), evaluated_at=args.now), args.output); return 0
        if args.cmd=='verify-grant': _write(verify_local_authorization_grant(_load(args.grant)), args.output); return 0
        if args.cmd=='revoke': raise RuntimeError('revocation requires typed in-process grant and ledger custody; inspect runtime module')
        if args.cmd=='validate-ledger': _write(validate_local_authorization_grant_ledger(_load(args.input)), args.output); return 0
        if args.cmd=='diff': print(json.dumps({'equal': _load(args.left)==_load(args.right)}, sort_keys=True)); return 0 if _load(args.left)==_load(args.right) else 65
        if args.cmd=='build-review-request': raise RuntimeError('build-review-request requires a typed HostLiveGrantReadinessEvaluation; use runtime API for sealed in-memory custody')
    except PermissionError as e: print(str(e), file=sys.stderr); return 69
    except RuntimeError as e: print(str(e), file=sys.stderr); return 78
    except ValueError as e: print(str(e), file=sys.stderr); return 64
    return 2
if __name__ == '__main__': raise SystemExit(main())
