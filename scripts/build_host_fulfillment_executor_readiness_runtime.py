#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typing import Sequence, Any

COMMANDS=("build-request","validate-request","plan","evaluate","validate-evaluation","validate-bundle","list-prerequisites","inspect-prerequisite","show-contract","show-backend-declaration","show-precondition-manifest","show-dry-run-plan","show-admission-packet","show-readiness-receipt","summarize","render-json","render-markdown","diff")

def _load(path:str) -> dict[str, Any]:
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data,dict): raise SystemExit('strict object input required')
    return data

def main(argv: Sequence[str] | None = None) -> int:
    ap=argparse.ArgumentParser(description='Build or inspect metadata-only host fulfillment executor contract readiness evidence; never executes, loads backends, grants fulfillment, mutates host state, calls Git, or performs effects.')
    ap.add_argument('command', nargs='?', choices=COMMANDS)
    ap.add_argument('--consumption-runtime-json', help='Strict JSON exported from typed runtime result; loose receipt-only JSON is rejected by evaluate.')
    ap.add_argument('--bundle-root')
    ap.add_argument('--output-root')
    ap.add_argument('--backend-label', default='declaration-only-not-loaded')
    ap.add_argument('--json-output')
    ns=ap.parse_args(argv)
    if ns.command is None:
        ap.print_help(); return 0
    out={"command":ns.command,"metadata_only":True,"no_git_operations":True,"execution_ready":False,"executor_implemented":False,"backend_loaded":False,"backend_invoked":False,"dry_run_executed":False,"control_plane_execution_admission_granted":False,"fulfillment_granted":False,"privileged_effect_admission_granted":False,"effect_performed":False,"host_mutation_performed":False}
    if ns.command in {"evaluate","build-request","validate-request","plan"} and not ns.consumption_runtime_json:
        raise SystemExit('explicit exact consumption-runtime input required')
    if ns.consumption_runtime_json:
        data=_load(ns.consumption_runtime_json)
        if 'consumption_receipt' in data and 'envelope' in data and 'ledger_entry' in data and 'ledger' in data:
            out['input_shape']='typed_runtime_result_json'
        else:
            raise SystemExit('loose JSON rejected: complete exact consumption runtime chain required')
    if ns.command.startswith('render-markdown'):
        text="# Host Fulfillment Executor Contract Readiness Runtime\n\n- execution_ready: False\n- backend_loaded: False\n- effect_performed: False\n"
        if ns.json_output: Path(ns.json_output).write_text(text,encoding='utf-8')
        print(text,end=''); return 0
    if ns.json_output: Path(ns.json_output).write_text(json.dumps(out,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps(out,sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
