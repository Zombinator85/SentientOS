#!/usr/bin/env python3
"""CLI for the operator-confirmed local diagnostic execution runtime."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command")
    for command in ("preflight","execute"):
        p=sub.add_parser(command)
        for name in ("execution-source-bundle-root","expected-source-bundle-digest","current-snapshot-json","current-verification-json","execution-time"): p.add_argument("--"+name,required=True)
        if command=="execute":
            p.add_argument("--output-root",required=True); p.add_argument("--confirm-local-diagnostic-write",action="store_true"); p.add_argument("--confirm-source-bundle-digest",required=True); p.add_argument("--confirm-effect-output-dir",required=True); p.add_argument("--confirmation-challenge-digest",required=True); p.add_argument("--correlation-id")
    p=sub.add_parser("validate-bundle"); p.add_argument("--bundle-root",required=True); p.add_argument("--expected-final-bundle-digest")
    p=sub.add_parser("validate-live-target"); p.add_argument("--bundle-root",required=True)
    p=sub.add_parser("latest-summary"); p.add_argument("--output-root",required=True)
    args=parser.parse_args(argv)
    if not args.command: parser.print_help(); return 0
    from sentientos.host_local_diagnostic_execution_runtime import HostLocalDiagnosticExecutionRuntimeCoordinator, validate_live_target, validate_persisted_execution_bundle
    try:
        if args.command in ("preflight","execute"):
            common={"execution_source_bundle_root":args.execution_source_bundle_root,"expected_source_bundle_digest":args.expected_source_bundle_digest,"current_snapshot":json.loads(Path(args.current_snapshot_json).read_text()),"current_verification":json.loads(Path(args.current_verification_json).read_text()),"execution_time":args.execution_time}
            coordinator=HostLocalDiagnosticExecutionRuntimeCoordinator()
            result=coordinator.preflight(**common) if args.command=="preflight" else coordinator.execute(**common,output_root=args.output_root,confirm_local_diagnostic_write=args.confirm_local_diagnostic_write,confirm_source_bundle_digest=args.confirm_source_bundle_digest,confirm_effect_output_dir=args.confirm_effect_output_dir,confirmation_challenge_digest=args.confirmation_challenge_digest,correlation_id=args.correlation_id)
        elif args.command=="validate-bundle": result=validate_persisted_execution_bundle(args.bundle_root,expected_final_bundle_digest=args.expected_final_bundle_digest)
        elif args.command=="validate-live-target": result=validate_live_target(args.bundle_root)
        else:
            latest=json.loads((Path(args.output_root)/"latest.json").read_text()); result=validate_persisted_execution_bundle(Path(args.output_root)/latest["execution_id"],expected_final_bundle_digest=latest["bundle_digest"])
        print(json.dumps(result.to_dict(),sort_keys=True,indent=2)); return 0 if result.status.endswith(("ready","completed","valid")) else 1
    except Exception as exc:
        print(json.dumps({"status":"blocked_host_local_diagnostic_execution_runtime","findings":[type(exc).__name__+":"+str(exc)]},sort_keys=True)); return 1
if __name__=="__main__": raise SystemExit(main())
