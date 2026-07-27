#!/usr/bin/env python3
"""CLI for operator-confirmed exact diagnostic rollback custody."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command")
    for command in ("preflight","rollback"):
        p=sub.add_parser(command)
        for name in ("execution-bundle-root","expected-execution-bundle-digest","current-snapshot-json","current-verification-json","rollback-time"): p.add_argument("--"+name,required=True)
        if command=="rollback":
            p.add_argument("--output-root",required=True); p.add_argument("--confirm-exact-rollback",action="store_true"); p.add_argument("--confirm-execution-bundle-digest",required=True); p.add_argument("--confirm-artifact-path",required=True); p.add_argument("--confirmation-challenge-digest",required=True); p.add_argument("--correlation-id")
    p=sub.add_parser("validate-bundle"); p.add_argument("--bundle-root",required=True); p.add_argument("--expected-final-bundle-digest"); p.add_argument("--expected-execution-bundle-digest")
    p=sub.add_parser("validate-live-postcondition"); p.add_argument("--bundle-root",required=True); p.add_argument("--expected-final-bundle-digest")
    p=sub.add_parser("latest-summary"); p.add_argument("--output-root",required=True)
    args=parser.parse_args(argv)
    if not args.command: parser.print_help(); return 0
    from sentientos.host_local_diagnostic_rollback_runtime import HostLocalDiagnosticRollbackRuntimeCoordinator, validate_live_rollback_postcondition, validate_persisted_rollback_bundle
    try:
        if args.command in ("preflight","rollback"):
            common={"execution_bundle_root":args.execution_bundle_root,"expected_execution_bundle_digest":args.expected_execution_bundle_digest,"current_snapshot":json.loads(Path(args.current_snapshot_json).read_text()),"current_verification":json.loads(Path(args.current_verification_json).read_text()),"rollback_time":args.rollback_time}; coordinator=HostLocalDiagnosticRollbackRuntimeCoordinator()
            result=coordinator.preflight(**common) if args.command=="preflight" else coordinator.rollback_execution(**common,output_root=args.output_root,confirm_exact_rollback=args.confirm_exact_rollback,confirm_execution_bundle_digest=args.confirm_execution_bundle_digest,confirm_artifact_path=args.confirm_artifact_path,confirmation_challenge_digest=args.confirmation_challenge_digest,correlation_id=args.correlation_id)
        elif args.command=="validate-bundle": result=validate_persisted_rollback_bundle(args.bundle_root,expected_final_bundle_digest=args.expected_final_bundle_digest,expected_execution_bundle_digest=args.expected_execution_bundle_digest)
        elif args.command=="validate-live-postcondition": result=validate_live_rollback_postcondition(args.bundle_root,expected_final_bundle_digest=args.expected_final_bundle_digest)
        else:
            pointer=json.loads((Path(args.output_root)/"latest.json").read_text()); result=validate_persisted_rollback_bundle(Path(args.output_root)/pointer["rollback_id"],expected_final_bundle_digest=pointer["bundle_digest"])
        print(json.dumps(result.to_dict(),sort_keys=True,indent=2)); return 0 if result.status in {"host_local_diagnostic_rollback_preflight_ready","host_local_diagnostic_rollback_completed","host_local_diagnostic_rollback_live_postcondition_valid"} else 1
    except Exception as exc:
        print(json.dumps({"status":"blocked_host_local_diagnostic_rollback_runtime","findings":[type(exc).__name__+":"+str(exc)]},sort_keys=True)); return 1
if __name__=="__main__": raise SystemExit(main())
