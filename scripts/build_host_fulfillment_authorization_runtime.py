#!/usr/bin/env python3
# mypy: disable-error-code="no-any-return,no-untyped-def,no-untyped-call,var-annotated,union-attr"
"""Build/inspect metadata-only host fulfillment authorization custody artifacts."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.host_fulfillment_authorization_runtime import build_source_ref, build_request_envelope, build_consumption_plan, validate_request_envelope, HostFulfillmentAuthorizationRuntimeCoordinator, render_markdown

def _load(path:str):
    return json.loads(Path(path).read_text(encoding='utf-8'))
def _dump(obj):
    print(json.dumps(obj.to_dict() if hasattr(obj,'to_dict') else obj, sort_keys=True, indent=2))
def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('command', choices=['build-request','validate-request','plan','validate-plan','consume','validate-evaluation','validate-receipt','validate-ledger','summarize','list-requests','inspect-request','list-consumptions','inspect-consumption','render-json','render-markdown','diff'])
    p.add_argument('--runtime-root', default=None); p.add_argument('--request'); p.add_argument('--issue-receipt'); p.add_argument('--grant'); p.add_argument('--verification'); p.add_argument('--ledger'); p.add_argument('--expiry'); p.add_argument('--revocation', action='append', default=[])
    p.add_argument('--actor', default='operator'); p.add_argument('--subsystem', default='operator_cli'); p.add_argument('--reason-code', action='append', default=['operator_requested_future_fulfillment']); p.add_argument('--note', default='')
    p.add_argument('--domain', default='future_cooling_fulfillment_authorization'); p.add_argument('--backend', default='future_cooling_backend_label'); p.add_argument('--scope', action='append', default=['future_cooling_scope']); p.add_argument('--target', action='append', default=[]); p.add_argument('--requested-time', default='1970-01-01T00:00:00+00:00'); p.add_argument('--not-before', default='1970-01-01T00:00:00+00:00'); p.add_argument('--not-after', default='1970-01-02T00:00:00+00:00'); p.add_argument('--apply', action='store_true')
    a=p.parse_args(argv)
    try:
        root=Path(a.runtime_root) if a.runtime_root else None
        coord=HostFulfillmentAuthorizationRuntimeCoordinator(root)
        if a.command in {'list-requests','list-consumptions'}:
            d=(coord.root/('requests' if a.command=='list-requests' else 'entries'))
            print(json.dumps(sorted(x.stem for x in d.glob('*.json')) if d.exists() else [])); return 0
        if a.command in {'inspect-request','inspect-consumption'}:
            kind='requests' if a.command=='inspect-request' else 'entries'; rid=a.request or ''
            print((coord.root/kind/f'{rid}.json').read_text()); return 0
        if a.command in {'validate-ledger','summarize','render-json','render-markdown'}:
            data=_load(str(coord.root/'ledger.json')) if (coord.root/'ledger.json').exists() else coord._load_ledger().to_dict()
            if a.command=='render-markdown': print('# Host Fulfillment Authorization Consumption Ledger\n')
            else: print(json.dumps(data, sort_keys=True, indent=2))
            return 0
        if not all([a.issue_receipt,a.grant,a.verification,a.ledger,a.expiry]):
            print('missing exact source inputs', file=sys.stderr); return 2
        issue,grant,ver,ledger,expiry=_load(a.issue_receipt),_load(a.grant),_load(a.verification),_load(a.ledger),_load(a.expiry)
        rev=[_load(x) for x in a.revocation]
        src=build_source_ref(issue,grant,ver,ledger,expiry,rev)
        env=_load(a.request) if a.request else build_request_envelope(requesting_actor=a.actor, requesting_subsystem=a.subsystem, reason_codes=a.reason_code, note=a.note, source_ref=src, requested_fulfillment_domain=a.domain, requested_backend_label=a.backend, requested_scope_labels=a.scope, requested_target_labels=a.target, requested_time=a.requested_time, expected_not_before=a.not_before, expected_not_after=a.not_after)
        if isinstance(env, dict):
            from sentientos.host_fulfillment_authorization_runtime import HostFulfillmentAuthorizationRequestEnvelope
            env=HostFulfillmentAuthorizationRequestEnvelope(**env)
        if a.command=='build-request': _dump(env); return 0
        if a.command=='validate-request':
            r=validate_request_envelope(env); print(json.dumps(r.__dict__, sort_keys=True)); return 0 if r.ok else 2
        plan=build_consumption_plan(env, src)
        if a.command in {'plan','validate-plan'}: _dump(plan); return 0
        ev,rec=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,rev,apply=a.apply)
        if a.command=='consume': _dump({'evaluation':ev.to_dict(),'runtime_receipt':rec.to_dict()}); return 0 if rec.status in {'consumption_recorded','replayed'} else (3 if rec.status=='not_applied' else 4)
        if a.command in {'validate-evaluation','validate-receipt','render-json'}: _dump(ev if a.command!='validate-receipt' else rec); return 0
        if a.command=='render-markdown': print(render_markdown(ev)); return 0
        if a.command=='diff': print(json.dumps({'diff':'not_applicable','metadata_only':True})); return 0
    except Exception as e:
        print(str(e), file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
