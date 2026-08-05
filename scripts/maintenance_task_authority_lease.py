#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, Sequence, cast
from sentientos import maintenance_task_authority_lease as m

def out(v: Any) -> None: print(m.canonical_json_bytes(v).decode())
def read(p: str) -> dict[str, Any]: return cast(dict[str, Any], json.loads(Path(p).read_text()))
def main(argv: Sequence[str] | None = None) -> int:
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    vg=sub.add_parser('verify-grant'); vg.add_argument('--grant',required=True); vg.add_argument('--evaluation-time',required=True)
    ad=sub.add_parser('admit'); ad.add_argument('--state-root',required=True); ad.add_argument('--candidate-set',required=True); ad.add_argument('--selection',required=True); ad.add_argument('--grant',required=True); ad.add_argument('--evaluation-time',required=True); ad.add_argument('--repo-root',default='.')
    vl=sub.add_parser('verify-lease'); vl.add_argument('--state-root',required=True); vl.add_argument('--lease-id',required=True); vl.add_argument('--evaluation-time',required=True); vl.add_argument('--repo-root',default='.')
    va=sub.add_parser('verify-action'); va.add_argument('--state-root',required=True); va.add_argument('--request',required=True); va.add_argument('--evaluation-time',required=True); va.add_argument('--repo-root',default='.')
    rv=sub.add_parser('revoke'); rv.add_argument('--state-root',required=True); rv.add_argument('--task-id',required=True); rv.add_argument('--lease-id',required=True); rv.add_argument('--operator-revocation-reference',required=True); rv.add_argument('--evaluation-time',required=True); rv.add_argument('--repo-root',default='.')
    ins=sub.add_parser('inspect'); ins.add_argument('--state-root',required=True); ins.add_argument('--lease-id',required=True); ins.add_argument('--repo-root',default='.')
    ns=ap.parse_args(argv)
    try:
        if ns.cmd=='verify-grant': r=m.verify_grant(read(ns.grant),evaluation_time=ns.evaluation_time); out(r); return 0 if r['status']=='grant_valid' else 2
        if ns.cmd=='admit': r=m.admit_selected_candidate(state_root=ns.state_root,candidate_set=read(ns.candidate_set),selection=read(ns.selection),operator_grant=read(ns.grant),evaluation_time=ns.evaluation_time,repo_root=ns.repo_root); out(r); return 0 if r['status'] in {'task_lease_ready','task_lease_already_ready','task_lease_recovered'} else 2
        if ns.cmd=='verify-lease': r=m.verify_lease(ns.state_root,ns.lease_id,evaluation_time=ns.evaluation_time,repo_root=ns.repo_root); out(r); return 0 if r['status']=='lease_active' else 2
        if ns.cmd=='verify-action': r=m.verify_action(ns.state_root,read(ns.request),evaluation_time=ns.evaluation_time,repo_root=ns.repo_root); out(r); return 0 if r['status']=='action_within_lease' else 2
        if ns.cmd=='revoke': r=m.revoke_lease(ns.state_root,task_id=ns.task_id,lease_id=ns.lease_id,operator_revocation_reference=ns.operator_revocation_reference,evaluation_time=ns.evaluation_time,repo_root=ns.repo_root); out(r); return 0 if r['status']=='lease_revoked' else 2
        lease=m.load_lease(ns.state_root,ns.lease_id,repo_root=ns.repo_root); out({'status':'lease_inspected','lease':lease}); return 0
    except Exception as e: out({'status':'error','reason_codes':[str(e)]}); return 2
if __name__=='__main__': sys.exit(main())
