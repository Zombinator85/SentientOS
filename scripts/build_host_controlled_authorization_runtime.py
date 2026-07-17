#!/usr/bin/env python
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.host_controlled_authorization_runtime import build_host_controlled_authorization_plan, render_markdown, validate_evaluation, persist_evidence_bundle

# This CLI is intentionally strict/read-only for imported JSON: it never promotes
# loose JSON into authoritative typed runtime evaluations. Real evaluation must be
# driven by in-process typed evidence from sentientosd/tests.

def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding='utf-8'))

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description='Inspect/validate host controlled authorization safety runtime artifacts')
    sub=p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('plan')
    for name in ('validate-plan','validate-evaluation','validate-bundle','summarize','list-gates','inspect-gate','list-contracts','inspect-contract','render-json','render-markdown','diff','evaluate'):
        sp=sub.add_parser(name); sp.add_argument('--input'); sp.add_argument('--left'); sp.add_argument('--right'); sp.add_argument('--gate-id'); sp.add_argument('--contract-id'); sp.add_argument('--output-root')
    ns=p.parse_args(argv)
    if ns.cmd == 'plan': print(json.dumps(build_host_controlled_authorization_plan().to_dict(), sort_keys=True)); return 0
    if ns.cmd == 'evaluate':
        print(json.dumps({'status':'blocked','reason':'typed_in_memory_host_execution_readiness_evaluation_required','live_authorization_granted':False,'host_mutation_performed':False}, sort_keys=True)); return 2
    data=_load(ns.input) if getattr(ns,'input',None) else {}
    if ns.cmd == 'validate-plan':
        ok = isinstance(data, dict) and data.get('metadata_only') is True and data.get('no_effect_authority') is True
        print(json.dumps({'ok': ok, 'findings': [] if ok else ['invalid_plan_bindings']})); return 0 if ok else 1
    if ns.cmd == 'validate-evaluation':
        ok = isinstance(data, dict) and data.get('no_authority') is True and data.get('schema_version') in (None, 'host_controlled_authorization_safety_runtime.v1')
        if not data.get('items'): ok=False
        print(json.dumps({'ok': ok, 'findings': [] if ok else ['loose_json_or_missing_typed_bindings']})); return 0 if ok else 1
    if ns.cmd == 'validate-bundle':
        required={'runtime_plan','admission_reference','source_evidence_manifest','controlled_authorization_contracts','schema_grant_records','revocation_schemas','authorization_ledgers','typed_safety_evidence_manifests','safety_gate_assessments','safety_gate_satisfaction_manifests','summary'}
        ok=isinstance(data,dict) and required.issubset(data)
        print(json.dumps({'ok':ok,'missing':sorted(required-set(data)) if isinstance(data,dict) else sorted(required)})); return 0 if ok else 1
    if ns.cmd == 'summarize': print(json.dumps(data.get('summary', data), sort_keys=True)); return 0
    if ns.cmd == 'list-gates': print(json.dumps(data.get('safety_gate_assessments', []), sort_keys=True)); return 0
    if ns.cmd == 'inspect-gate':
        rows=data.get('safety_gate_assessments',[]); print(json.dumps(next((r for r in rows if r.get('assessment_id')==ns.gate_id), {}), sort_keys=True)); return 0
    if ns.cmd == 'list-contracts': print(json.dumps(data.get('controlled_authorization_contracts', []), sort_keys=True)); return 0
    if ns.cmd == 'inspect-contract':
        rows=data.get('controlled_authorization_contracts',[]); print(json.dumps(next((r for r in rows if r.get('contract_id')==ns.contract_id), {}), sort_keys=True)); return 0
    if ns.cmd == 'render-json': print(json.dumps(data, sort_keys=True)); return 0
    if ns.cmd == 'render-markdown':
        s=data.get('summary',{}); print(f"# Host Controlled Authorization Safety Runtime\n\n- Status: `{s.get('status','unknown')}`\n- Live authorization granted: `False`\n- Host mutation performed: `False`\n"); return 0
    if ns.cmd == 'diff':
        l=_load(ns.left); r=_load(ns.right); print(json.dumps({'same': l==r, 'left_keys': sorted(l) if isinstance(l,dict) else [], 'right_keys': sorted(r) if isinstance(r,dict) else []}, sort_keys=True)); return 0
    return 1
if __name__ == '__main__': raise SystemExit(main())
