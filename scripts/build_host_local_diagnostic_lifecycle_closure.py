from __future__ import annotations
import argparse, json
from sentientos.host_local_diagnostic_lifecycle_closure import build_lifecycle_closure, load_latest_summary, validate_lifecycle_closure

def main() -> int:
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="command",required=True)
    b=s.add_parser("build")
    for name in ("execution-bundle-root","execution-bundle-digest","rollback-bundle-root","rollback-bundle-digest","closure-time","output-root"): b.add_argument("--"+name,required=True)
    b.add_argument("--correlation-id")
    v=s.add_parser("validate"); v.add_argument("--packet-root",required=True); v.add_argument("--expected-packet-digest")
    l=s.add_parser("latest-summary"); l.add_argument("--output-root",required=True)
    a=p.parse_args()
    if a.command=="build": result=build_lifecycle_closure(execution_bundle_root=a.execution_bundle_root,execution_bundle_digest=a.execution_bundle_digest,rollback_bundle_root=a.rollback_bundle_root,rollback_bundle_digest=a.rollback_bundle_digest,closure_time=a.closure_time,output_root=a.output_root,correlation_id=a.correlation_id)
    elif a.command=="validate": result=validate_lifecycle_closure(a.packet_root,expected_packet_digest=a.expected_packet_digest)
    else: result=load_latest_summary(a.output_root)
    print(json.dumps(result.to_dict(),sort_keys=True)); return 0 if result.status=="host_local_diagnostic_lifecycle_closure_valid" else 1
if __name__=="__main__": raise SystemExit(main())
