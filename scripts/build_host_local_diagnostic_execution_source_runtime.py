#!/usr/bin/env python3
"""CLI for strict diagnostic execution-source custody evidence."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sentientos.host_local_diagnostic_execution_source_runtime import HostLocalDiagnosticExecutionSourceRuntimeCoordinator,load_latest_evaluation,validate_persisted_execution_source_bundle

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="command")
    e=s.add_parser("evaluate")
    for x in ("admission-bundle-root","dry-run-bundle-root","readiness-bundle-root","current-snapshot-json","current-verification-json","effect-output-dir","output-root"): e.add_argument("--"+x,required=True)
    e.add_argument("--correlation-id")
    v=s.add_parser("validate-bundle"); v.add_argument("--bundle-root",required=True)
    l=s.add_parser("latest-summary"); l.add_argument("--output-root",required=True)
    a=p.parse_args(argv)
    if not a.command: p.print_help(); return 0
    if a.command=="validate-bundle": out=validate_persisted_execution_source_bundle(a.bundle_root).to_dict(); ok=out["ok"]
    elif a.command=="latest-summary":
        ev=load_latest_evaluation(a.output_root); out=ev.to_dict() if ev else {"status":"latest_summary_unavailable"}; ok=ev is not None
    else:
        try:
            snap=json.loads(Path(a.current_snapshot_json).read_text()); ver=json.loads(Path(a.current_verification_json).read_text())
            ev=HostLocalDiagnosticExecutionSourceRuntimeCoordinator().evaluate(admission_bundle_root=a.admission_bundle_root,dry_run_bundle_root=a.dry_run_bundle_root,readiness_bundle_root=a.readiness_bundle_root,current_snapshot=snap,current_verification=ver,effect_output_dir=a.effect_output_dir,output_root=a.output_root,correlation_id=a.correlation_id); out=ev.to_dict(); ok=ev.status=="host_local_diagnostic_execution_source_ready"
        except Exception as exc: out={"status":"blocked_host_local_diagnostic_execution_source_runtime","findings":[type(exc).__name__+":"+str(exc)]}; ok=False
    print(json.dumps(out,sort_keys=True,indent=2)); return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
