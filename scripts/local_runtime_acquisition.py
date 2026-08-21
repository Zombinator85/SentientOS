"""Inspect or explicitly execute bounded runtime artifact acquisition."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from sentientos.local_runtime_acquisition import AcquisitionError, acquire_runtime_artifact, authorization_for, default_escrow_root

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provisioning-plan", type=Path, required=True)
    parser.add_argument("--runtime-catalog", type=Path, default=Path("manifests/local-runtime-catalog-v2.json"))
    parser.add_argument("--escrow-root", type=Path, default=default_escrow_root())
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-plan-digest")
    args = parser.parse_args()
    plan = json.loads(args.provisioning_plan.read_text(encoding="utf-8"))
    authorization = None
    if args.execute:
        if args.confirm_plan_digest != plan.get("provisioning_plan_digest"):
            print(json.dumps({"status":"blocked", "reason_code":"confirmed_plan_digest_mismatch"}, sort_keys=True)); return 2
        authorization = authorization_for(plan, args.escrow_root, operator_confirmed=True)
    try:
        result = acquire_runtime_artifact(plan, catalog_path=args.runtime_catalog, escrow_root=args.escrow_root,
                                          authorization=authorization, execute=args.execute)
    except AcquisitionError as exc:
        print(json.dumps({"status":"blocked", "reason_code":exc.code}, sort_keys=True)); return 2
    print(json.dumps(result, sort_keys=True, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
