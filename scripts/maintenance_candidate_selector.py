#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from typing import Any, Sequence
from pathlib import Path
from sentientos.maintenance_candidate import adapt_explicit_candidate, adapt_genesis_metadata, adapt_governed_signal, adapt_work_item_packet, canonical_json_bytes, normalize_candidate_set
from sentientos.maintenance_candidate_selector import build_policy, select_candidate, selection_bytes

def _load(p: str) -> dict[str, Any]:
    value = json.loads(Path(p).read_text(encoding='utf-8'))
    return dict(value)
def _write(obj: dict[str, Any], out: str | None) -> None:
    data=canonical_json_bytes(obj)+b'\n'
    if out: Path(out).write_bytes(data)
    else: sys.stdout.buffer.write(data)

def main(argv: Sequence[str] | None = None) -> int:
    ap=argparse.ArgumentParser(description='maintenance candidate selector')
    sub=ap.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('adapt'); a.add_argument('--source-kind',required=True,choices=['governed_improvement_signal','normalized_work_item','genesis_need','explicit_maintenance_candidate']); a.add_argument('--input',required=True); a.add_argument('--base-sha',required=True); a.add_argument('--output')
    n=sub.add_parser('normalize'); n.add_argument('--input',action='append',required=True); n.add_argument('--output')
    s=sub.add_parser('select'); s.add_argument('--candidate-set',required=True); s.add_argument('--policy',required=True); s.add_argument('--journal-state-root'); s.add_argument('--output')
    i=sub.add_parser('inspect'); i.add_argument('--input',required=True)
    ns=ap.parse_args(argv)
    try:
        if ns.cmd=='adapt':
            r=_load(ns.input)
            if ns.source_kind=='governed_improvement_signal': c=adapt_governed_signal(r,base_repository_sha=ns.base_sha)
            elif ns.source_kind=='normalized_work_item': c=adapt_work_item_packet(r,base_repository_sha=ns.base_sha)
            elif ns.source_kind=='genesis_need': c=adapt_genesis_metadata(r,base_repository_sha=ns.base_sha)
            else: c=adapt_explicit_candidate(r,base_repository_sha=ns.base_sha)
            _write(c.to_dict(),ns.output); return 0 if c.lifecycle_disposition not in {'candidate_contradicted','candidate_insufficient_metadata'} else 2
        if ns.cmd=='normalize':
            
            from sentientos.maintenance_candidate_selector import candidate_from_dict
            vals=[]
            for p in ns.input:
                d=_load(p)
                vals.append(candidate_from_dict(d) if d.get('schema_version')=='sentientos.maintenance_candidate:v1' else adapt_explicit_candidate(d,base_repository_sha=d.get('base_repository_sha','')))
            cs=normalize_candidate_set(vals)
            _write(cs,ns.output); return 2 if cs['contradictions'] else 0
        if ns.cmd=='select':
            sel=select_candidate(_load(ns.candidate_set), build_policy(_load(ns.policy)), journal_state_root=ns.journal_state_root)
            sys.stdout.buffer.write(selection_bytes(sel)) if not ns.output else Path(ns.output).write_bytes(selection_bytes(sel))
            return 2 if sel.get('result_status') in {'journal_state_invalid','candidate_set_invalid','selection_blocked'} else 0
        obj=_load(ns.input); _write({'schema_version':obj.get('schema_version'),'digest':obj.get('aggregate_digest') or obj.get('selection_digest') or obj.get('canonical_candidate_digest'),'result_status':obj.get('result_status')},None); return 0
    except Exception as e:
        _write({'status':'error','reason_code':str(e)},None); return 2
if __name__=='__main__': raise SystemExit(main())
