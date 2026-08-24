"""Inspect or execute selected local runtime backend verification."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.local_runtime_backend_verification import (RuntimeBackendVerificationError,
    authorization_for, compose_verification_plan, verify_runtime_backend)

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--installation-plan",type=Path,required=True)
    p.add_argument("--installation-receipt",type=Path,required=True); p.add_argument("--import-plan",type=Path,required=True)
    p.add_argument("--import-receipt",type=Path,required=True); p.add_argument("--verification-receipt-root",type=Path,required=True)
    p.add_argument("--execute",action="store_true"); p.add_argument("--confirm-verification-plan-digest"); a=p.parse_args()
    try:
        load=lambda x: json.loads(x.read_text(encoding="utf-8")); ip,ir,rp,rr=map(load,(a.installation_plan,a.installation_receipt,a.import_plan,a.import_receipt))
        plan=compose_verification_plan(ip,ir,rp,rr,a.verification_receipt_root); auth=None
        if a.execute:
            if a.confirm_verification_plan_digest != plan["runtime_backend_verification_plan_digest"]: raise RuntimeBackendVerificationError("runtime_backend_authorization_invalid")
            auth=authorization_for(plan,operator_confirmed=True)
        result=verify_runtime_backend(plan,ip,ir,rp,rr,authorization=auth,execute=a.execute)
    except (OSError,json.JSONDecodeError,RuntimeBackendVerificationError) as exc:
        print(json.dumps({"status":"blocked","reason_code":getattr(exc,"code","runtime_backend_result_invalid")},sort_keys=True)); return 2
    print(json.dumps(result,sort_keys=True,indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
