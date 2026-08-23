"""Inspect or execute a bounded installed-runtime import verification."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from sentientos.local_runtime_import_verification import (RuntimeImportVerificationError,
    authorization_for, compose_verification_plan, verify_runtime_import)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installation-plan", required=True, type=Path)
    parser.add_argument("--installation-receipt", required=True, type=Path)
    parser.add_argument("--verification-receipt-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-verification-plan-digest")
    args = parser.parse_args()
    try:
        installation_plan = json.loads(args.installation_plan.read_text(encoding="utf-8"))
        installation_receipt = json.loads(args.installation_receipt.read_text(encoding="utf-8"))
        plan = compose_verification_plan(installation_plan, installation_receipt, args.verification_receipt_root)
        auth = None
        if args.execute:
            if args.confirm_verification_plan_digest != plan["runtime_import_verification_plan_digest"]:
                raise RuntimeImportVerificationError("runtime_import_authorization_invalid")
            auth = authorization_for(plan, operator_confirmed=True)
        result = verify_runtime_import(plan, installation_plan, installation_receipt,
            authorization=auth, execute=args.execute)
    except (OSError, json.JSONDecodeError, RuntimeImportVerificationError) as exc:
        code = exc.code if isinstance(exc, RuntimeImportVerificationError) else "installation_not_verified"
        print(json.dumps({"status": "blocked", "reason_code": code}, sort_keys=True)); return 2
    print(json.dumps(result, sort_keys=True, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
