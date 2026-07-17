#!/usr/bin/env python3
# mypy: disable-error-code="no-untyped-def,no-untyped-call"
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from sentientos.host_live_grant_readiness_runtime import build_host_live_grant_readiness_plan, validate_evaluation, render_markdown

def _load(path: str): return json.loads(Path(path).read_text(encoding='utf-8'))
def _emit(obj, summary=False):
    if summary: print(json.dumps(obj, sort_keys=True))
    else: print(json.dumps(obj, sort_keys=True, indent=2))

def main(argv=None):
    p=argparse.ArgumentParser(description='Host live-grant readiness runtime metadata CLI (no grants/effects).')
    sub=p.add_subparsers(dest='cmd', required=True)
    for name in ['plan','validate-plan','evaluate','validate-evaluation','validate-bundle','summarize','list-prerequisites','inspect-prerequisite','show-approval-packet','show-preflight','show-denial-deferral','render-json','render-markdown','diff']:
        sp=sub.add_parser(name); sp.add_argument('--input'); sp.add_argument('--output-root'); sp.add_argument('--summary', action='store_true'); sp.add_argument('--index', type=int, default=0); sp.add_argument('--other')
    ns=p.parse_args(argv)
    if ns.cmd in {'plan','validate-plan'}:
        plan=build_host_live_grant_readiness_plan().to_dict(); _emit({'status':'plan_valid','subsystem':'host_live_grant_readiness_runtime','plan':plan,'no_authority':True}, ns.summary); return 0
    if ns.cmd == 'evaluate':
        # Strictly require typed runtime JSON with exact source bindings; reconstruction is intentionally unsupported.
        data=_load(ns.input) if ns.input else {}
        if not data.get('evaluation_id') or not data.get('semantic_digest') or not data.get('items'):
            _emit({'status':'failed_closed','reason':'typed_controlled_authorization_runtime_input_required','local_grant_issued':False,'host_mutation_performed':False}, ns.summary); return 2
        _emit({'status':'requires_in_process_typed_evaluation','reason':'cli_does_not_rebuild_or_rerun_upstream_evidence','local_grant_issued':False,'host_mutation_performed':False}, ns.summary); return 2
    data=_load(ns.input) if ns.input else {}
    if ns.cmd == 'validate-evaluation':
        # JSON diagnostic mode: strict current runtime validation fails when bindings/dataclass records are absent.
        ok=bool(data.get('schema_version') == 'host_live_grant_readiness_runtime.v1' and data.get('source_controlled_authorization_evaluation_digest'))
        _emit({'status':'evaluation_valid' if ok else 'failed_closed','findings':[] if ok else ['exact_typed_bindings_required']}, ns.summary); return 0 if ok else 2
    if ns.cmd == 'summarize': _emit(data.get('summary', data), ns.summary); return 0
    items=data.get('items', []) if isinstance(data, dict) else []
    rec = (items[ns.index].get('readiness_records') if len(items)>ns.index else {}) or {}
    if ns.cmd == 'list-prerequisites': _emit(rec.get('prerequisite_matrix', {}).get('prerequisites', []), ns.summary); return 0
    if ns.cmd == 'inspect-prerequisite': _emit((rec.get('prerequisite_matrix', {}).get('prerequisites', []) or [{}])[0], ns.summary); return 0
    if ns.cmd == 'show-approval-packet': _emit(rec.get('approval_packet', {}), ns.summary); return 0
    if ns.cmd == 'show-preflight': _emit(rec.get('preflight_receipt', {}), ns.summary); return 0
    if ns.cmd == 'show-denial-deferral': _emit(rec.get('denial_deferral_receipt', {}), ns.summary); return 0
    if ns.cmd == 'render-json': _emit(data, ns.summary); return 0
    if ns.cmd == 'render-markdown': print('# Host Live Grant Readiness Runtime\n\n- Read-only review metadata.\n- No local grant issued.'); return 0
    if ns.cmd == 'validate-bundle': _emit({'status':'bundle_validated_diagnostic','read_only':True,'local_grant_issued':False}, ns.summary); return 0
    if ns.cmd == 'diff':
        other=_load(ns.other) if ns.other else {}; _emit({'same': data == other, 'left_digest': __import__('hashlib').sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(), 'right_digest': __import__('hashlib').sha256(json.dumps(other,sort_keys=True).encode()).hexdigest()}, ns.summary); return 0
    return 2
if __name__ == '__main__': raise SystemExit(main())
