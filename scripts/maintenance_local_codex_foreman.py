#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from sentientos.maintenance_local_codex_foreman import *

def load_config(p:Path)->LocalCodexForemanConfig: return LocalCodexForemanConfig.from_mapping(json.loads(p.read_text()))
def main(argv: list[str] | None = None) -> int:
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    for name in ('probe','prepare','run','resume','cancel','inspect','verify-result'):
        s=sub.add_parser(name); s.add_argument('--foreman-configuration',required=True); s.add_argument('--lease',required=False); s.add_argument('--request',required=False); s.add_argument('--session',required=False); s.add_argument('--instruction-artifact-root',required=False); s.add_argument('--evaluation-time',default='9999')
    ns=ap.parse_args(argv); cfg=load_config(Path(ns.foreman_configuration))
    try:
        if ns.cmd=='probe': out=probe_local_codex_cli(cfg); code=0 if out['status']=='capability_probe_ready' else 2
        elif ns.cmd=='prepare': out=prepare_worktree(cfg,json.loads(Path(ns.lease).read_text()),json.loads(Path(ns.session).read_text())['session_id']); code=0
        elif ns.cmd=='run': out=run_local_codex_session(cfg,json.loads(Path(ns.lease).read_text()),json.loads(Path(ns.request).read_text()),json.loads(Path(ns.session).read_text()),Path(ns.instruction_artifact_root)); code=0 if out.get('status')=='implementation_ready_for_validation' else 2
        elif ns.cmd=='resume': out=resume_local_codex_session(cfg,json.loads(Path(ns.lease).read_text()),json.loads(Path(ns.request).read_text()),json.loads(Path(ns.session).read_text()),Path(ns.instruction_artifact_root),ns.evaluation_time); code=0 if out.get('status')=='implementation_ready_for_validation' else 2
        elif ns.cmd=='cancel': sess=json.loads(Path(ns.session).read_text()); out=cancel_local_codex_session(cfg,sess['task_id'],sess['session_id']); code=0
        else: sid=json.loads(Path(ns.session).read_text())['session_id']; out=inspect_local_codex_session(cfg,sid); code=0 if out.get('status') in TERMINAL_STATUSES else 2
    except Exception as e:
        out={'status':'foreman_cli_error','reason':str(e)}; code=2
    print(json.dumps(out,sort_keys=True)); return code
if __name__=='__main__': raise SystemExit(main())
