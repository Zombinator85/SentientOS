#!/usr/bin/env python3
# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type,union-attr"
"""CLI for host execution-readiness authorization-review runtime artifacts."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.host_execution_readiness_runtime import build_host_execution_readiness_plan

EXIT_MALFORMED_SOURCE=2; EXIT_ADMISSION_DENIED=3; EXIT_ADMISSION_DEFERRED=4; EXIT_QUARANTINED=5; EXIT_SOURCE_CONFLICT=6; EXIT_STALE_SUPERVISOR=7; EXIT_BUNDLE_VALIDATION=8

def _read(path: str):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception as exc: raise SystemExit(f"malformed json: {exc}")

def _write(obj, out):
    text=json.dumps(obj, sort_keys=True, indent=2)
    if out: Path(out).write_text(text+"\n", encoding='utf-8')
    print(text)

def cmd_plan(args): _write(build_host_execution_readiness_plan().to_dict(), args.output)
def cmd_validate_plan(args):
    d=_read(args.plan); ok=isinstance(d,dict) and d.get('evidence_only') is True and d.get('no_effect_authority') is True
    _write({'status':'valid' if ok else 'invalid','findings':[] if ok else ['plan_not_evidence_only']}, args.output); return 0 if ok else EXIT_BUNDLE_VALIDATION
def cmd_summarize(args):
    d=_read(args.evaluation); summary=d.get('summary',{}) if isinstance(d,dict) else {}; _write(summary,args.output)
def cmd_list(args):
    d=_read(args.evaluation); _write({'items':[i.get('item_id') for i in d.get('items',[]) if isinstance(i,dict)]},args.output)
def cmd_inspect(args):
    d=_read(args.evaluation)
    for i in d.get('items',[]):
        if isinstance(i,dict) and i.get('item_id')==args.item_id: _write(i,args.output); return 0
    _write({'status':'not_found','item_id':args.item_id},args.output); return 1
def cmd_render_json(args): _write(_read(args.input), args.output)
def cmd_render_markdown(args):
    d=_read(args.evaluation); text=f"# Host Execution Readiness Runtime\n\n- Evaluation: `{d.get('evaluation_id','unknown')}`\n- Authority: review-only; no execution.\n"
    if args.output: Path(args.output).write_text(text, encoding='utf-8')
    print(text); return 0
def cmd_diff(args):
    a=_read(args.before); b=_read(args.after); _write({'same': a==b, 'before_evaluation_id': a.get('evaluation_id'), 'after_evaluation_id': b.get('evaluation_id')}, args.output)
def cmd_validate_evaluation(args):
    d=_read(args.evaluation); findings=[]
    if d.get('no_authority') is not True: findings.append('authority_flag_true')
    for i in d.get('items',[]):
        if isinstance(i,dict) and i.get('valid_source') and i.get('future_authorization_grant_schema',{}).get('authorization_granted'): findings.append('future_schema_claims_grant')
    _write({'status':'valid' if not findings else 'invalid','findings':findings},args.output); return 0 if not findings else EXIT_BUNDLE_VALIDATION
def cmd_validate_item(args): return cmd_validate_evaluation(args)
def cmd_validate_bundle(args):
    root=Path(args.bundle); ok=root.exists() and (root/'summary.json').exists()
    _write({'status':'valid' if ok else 'invalid','findings':[] if ok else ['missing_summary_json']}, args.output); return 0 if ok else EXIT_BUNDLE_VALIDATION
def cmd_evaluate(args):
    if not args.privilege_review_evaluation: _write({'status':'malformed_source','no_authority':True}, args.output); return EXIT_MALFORMED_SOURCE
    src=_read(args.privilege_review_evaluation)
    if not isinstance(src,dict) or not src.get('evaluation_id'): _write({'status':'malformed_source','no_authority':True}, args.output); return EXIT_MALFORMED_SOURCE
    # Full typed evaluation is intentionally library-owned; CLI refuses to fabricate records from loose JSON.
    _write({'status':'source_requires_typed_runtime_context','evaluation_id':src.get('evaluation_id'),'no_authority':True,'authorization_granted':False,'execution_triggered':False}, args.output); return EXIT_MALFORMED_SOURCE

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd', required=True)
    def addout(sp): sp.add_argument('--output')
    for name, fn in [('plan',cmd_plan)]: sp=sub.add_parser(name); addout(sp); sp.set_defaults(fn=fn)
    sp=sub.add_parser('evaluate'); sp.add_argument('--privilege-review-evaluation'); sp.add_argument('--output-root'); addout(sp); sp.set_defaults(fn=cmd_evaluate)
    for name, fn, arg in [('validate-plan',cmd_validate_plan,'plan'),('validate-evaluation',cmd_validate_evaluation,'evaluation'),('validate-item',cmd_validate_item,'evaluation'),('summarize',cmd_summarize,'evaluation'),('list-items',cmd_list,'evaluation'),('render-markdown',cmd_render_markdown,'evaluation')]: sp=sub.add_parser(name); sp.add_argument(arg); addout(sp); sp.set_defaults(fn=fn)
    sp=sub.add_parser('inspect-item'); sp.add_argument('evaluation'); sp.add_argument('item_id'); addout(sp); sp.set_defaults(fn=cmd_inspect)
    sp=sub.add_parser('validate-bundle'); sp.add_argument('bundle'); addout(sp); sp.set_defaults(fn=cmd_validate_bundle)
    sp=sub.add_parser('render-json'); sp.add_argument('input'); addout(sp); sp.set_defaults(fn=cmd_render_json)
    sp=sub.add_parser('diff'); sp.add_argument('before'); sp.add_argument('after'); addout(sp); sp.set_defaults(fn=cmd_diff)
    a=p.parse_args(argv); return a.fn(a) or 0
if __name__=='__main__': raise SystemExit(main())
