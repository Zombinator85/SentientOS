# mypy: ignore-errors
#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.genesis_reviewed_adoption import *

def _load(path: str): return json.loads(Path(path).read_text(encoding='utf-8'))
def _write(path: str|None, payload):
    text=canonical_json(payload)+"\n"
    if path: Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(text, encoding='utf-8')
    else: print(text, end='')

def packet_from_dict(d):
    c=ReviewedGenesisCandidate(**d['candidate']); dd=dict(d); dd['candidate']=c; return GenesisCandidateReviewPacket(**dd)
def decision_from_dict(d): return GenesisCandidateReviewDecision(**d)
def plan_from_dict(d): return GenesisReviewedAdoptionPlan(**d)

def main(argv=None):
    p=argparse.ArgumentParser(description='Build and inspect reviewed Genesis adoption custody artifacts')
    sub=p.add_subparsers(dest='cmd', required=True)
    for name in ['validate-review-packet','validate-decision','validate-plan','validate-receipt','summarize','render-json','render-markdown','inspect']:
        s=sub.add_parser(name); s.add_argument('input'); s.add_argument('--packet'); s.add_argument('--output')
    s=sub.add_parser('decide'); s.add_argument('--packet', required=True); s.add_argument('--disposition', required=True); s.add_argument('--reviewer', required=True); s.add_argument('--reviewer-role', default='operator'); s.add_argument('--reason-code', action='append', default=[]); s.add_argument('--note', default=''); s.add_argument('--output')
    s=sub.add_parser('plan'); s.add_argument('--packet', required=True); s.add_argument('--decision', required=True); s.add_argument('--runtime-root', required=True); s.add_argument('--output')
    s=sub.add_parser('execute'); s.add_argument('--packet', required=True); s.add_argument('--decision', required=True); s.add_argument('--plan', required=True); s.add_argument('--runtime-root', required=True); s.add_argument('--apply', action='store_true'); s.add_argument('--output')
    s=sub.add_parser('diff'); s.add_argument('left'); s.add_argument('right')
    s=sub.add_parser('build-review-packet'); s.add_argument('--evaluation-json', required=True); s.add_argument('--output')
    ns=p.parse_args(argv)
    try:
        if ns.cmd=='decide':
            pkt=packet_from_dict(_load(ns.packet)); _write(ns.output, decide(pkt, disposition=ns.disposition, reviewer=ns.reviewer, reviewer_role=ns.reviewer_role, reason_codes=ns.reason_code).to_dict()); return 0
        if ns.cmd=='plan':
            pkt=packet_from_dict(_load(ns.packet)); dec=decision_from_dict(_load(ns.decision)); _write(ns.output, build_plan(pkt, dec, runtime_root=ns.runtime_root).to_dict()); return 0
        if ns.cmd=='execute':
            if not ns.apply: print('explicit --apply required', file=sys.stderr); return 10
            res=GenesisReviewedAdoptionCoordinator(ns.runtime_root).execute(packet_from_dict(_load(ns.packet)), decision_from_dict(_load(ns.decision)), plan_from_dict(_load(ns.plan)), apply=True)
            _write(ns.output, res.to_dict()); return 0 if getattr(res,'status','')=='adopted' else 20
        if ns.cmd=='validate-review-packet': r=validate_review_packet(_load(ns.input)); _write(ns.output, {'valid':r.valid,'findings':r.findings}); return 0 if r.valid else 2
        if ns.cmd=='validate-decision': r=validate_decision(_load(ns.input), packet_from_dict(_load(ns.packet)) if ns.packet else None); _write(ns.output, {'valid':r.valid,'findings':r.findings}); return 0 if r.valid else 3
        if ns.cmd=='validate-plan': d=_load(ns.input); ok=d.get('schema_version')==PLAN_SCHEMA_VERSION and d.get('repository_source_mutation') is False; _write(ns.output, {'valid':ok,'findings':[] if ok else ['invalid_plan']}); return 0 if ok else 4
        if ns.cmd=='validate-receipt': d=_load(ns.input); ok=d.get('schema_version') in {RECEIPT_SCHEMA_VERSION,ROLLBACK_SCHEMA_VERSION}; _write(ns.output, {'valid':ok,'status':d.get('status')}); return 0 if ok else 5
        if ns.cmd in {'summarize','render-json','inspect'}: d=_load(ns.input); _write(ns.output, {'schema_version':d.get('schema_version'),'id':d.get('review_packet_id') or d.get('decision_id') or d.get('plan_id') or d.get('receipt_id') or d.get('rollback_id'),'digest':d.get('review_packet_digest') or d.get('decision_digest') or d.get('plan_digest') or d.get('receipt_digest') or d.get('rollback_digest'),'status':d.get('status') or d.get('disposition')}); return 0
        if ns.cmd=='render-markdown': d=_load(ns.input); md=f"# Genesis reviewed adoption artifact\n\n- schema: `{d.get('schema_version')}`\n- status: `{d.get('status') or d.get('disposition','n/a')}`\n"; Path(ns.output).write_text(md,encoding='utf-8') if ns.output else print(md); return 0
        if ns.cmd=='diff': print(canonical_json({'equal': digest_payload(_load(ns.left))==digest_payload(_load(ns.right))})); return 0
        if ns.cmd=='build-review-packet': print('build-review-packet requires in-process GenesisCandidateEvaluation; use Python API', file=sys.stderr); return 6
    except GenesisReviewedAdoptionValidationError as e:
        print(str(e), file=sys.stderr); return 11
    except GenesisReviewedAdoptionConflict as e:
        print(str(e), file=sys.stderr); return 12
if __name__=='__main__': raise SystemExit(main())
