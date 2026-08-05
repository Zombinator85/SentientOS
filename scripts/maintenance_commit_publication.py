#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, Sequence
from sentientos import maintenance_commit_publication as m
from sentientos import maintenance_task_authority_lease as lease_mod

def load(p: str | Path) -> dict[str, Any]: return dict(json.loads(Path(p).read_text(encoding='utf-8')))
def emit(o: Any) -> None: print(m.canonical_json_bytes(o).decode())

def main(argv: Sequence[str] | None=None) -> int:
    ap=argparse.ArgumentParser(description='maintenance commit publication')
    ap.add_argument('--state-root', required=True); ap.add_argument('--repository-root', required=True); ap.add_argument('--worktree-root')
    ap.add_argument('--task-id', required=True); ap.add_argument('--lease-id', required=True); ap.add_argument('--validation-result'); ap.add_argument('--landing-policy', required=True); ap.add_argument('--evaluation-time', required=True); ap.add_argument('--publication-id')
    sub=ap.add_subparsers(dest='cmd', required=True)
    for c in ['plan-commit','commit','enqueue','list-queued','publish-once','inspect-commit','inspect-publication','verify-commit','verify-publication']: sub.add_parser(c)
    ns=ap.parse_args(argv)
    try:
        lease=lease_mod.load_lease(ns.state_root, ns.lease_id, repo_root=ns.repository_root); pol=load(ns.landing_policy)
        if lease.get('task_id')!=ns.task_id: raise m.MaintenanceLandingError('task_lease_mismatch')
        val=load(ns.validation_result) if ns.validation_result else {}
        if ns.cmd=='plan-commit': emit(m.build_commit_plan(state_root=ns.state_root,repository_root=ns.repository_root,worktree_root=ns.worktree_root,lease=lease,validation_result=val,landing_policy=pol,evaluation_time=ns.evaluation_time)); return 0
        if ns.cmd in {'commit','enqueue'}: emit(m.create_commit_and_enqueue(state_root=ns.state_root,repository_root=ns.repository_root,worktree_root=ns.worktree_root,lease=lease,validation_result=val,landing_policy=pol,evaluation_time=ns.evaluation_time)); return 0
        if ns.cmd=='list-queued': emit({'queued':m.list_queued_requests(ns.state_root, repo_root=ns.repository_root)}); return 0
        if ns.cmd=='publish-once': emit(m.publish_one_maintenance_request(state_root=ns.state_root,repository_root=ns.repository_root,lease=lease,landing_policy=pol,publication_id=ns.publication_id,evaluation_time=ns.evaluation_time)); return 0
        if ns.cmd in {'inspect-commit','verify-commit'}:
            files=list((Path(ns.state_root)/'maintenance_commit_results').glob('*.json')) if (Path(ns.state_root)/'maintenance_commit_results').exists() else []
            out=[load(p) for p in files]; emit({'commit_results':out,'status':'commit_verified' if out else 'commit_missing'}); return 0 if out else 2
        if ns.cmd in {'inspect-publication','verify-publication'}:
            pid=ns.publication_id; p=Path(ns.state_root)/'maintenance_publication_results'/(pid+'.json')
            emit(load(p) if p.exists() else {'status':'publication_missing'}); return 0 if p.exists() else 2
    except Exception as e:
        emit({'status':'error','reason_code':str(e)}); return 2
    return 2
if __name__=='__main__': raise SystemExit(main())
