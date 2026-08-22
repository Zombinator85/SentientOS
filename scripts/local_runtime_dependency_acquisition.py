"""Inspect or explicitly acquire a selected exact dependency bundle."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from sentientos.local_runtime_dependencies import load_dependency_catalog
from sentientos.local_runtime_dependency_acquisition import DependencyAcquisitionError, acquire_dependency_bundle, authorization_for, default_dependency_escrow_root

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependency-plan", type=Path, required=True)
    parser.add_argument("--dependency-catalog", type=Path, default=Path("manifests/local-runtime-dependency-catalog-v1.json"))
    parser.add_argument("--escrow-root", type=Path, default=default_dependency_escrow_root())
    parser.add_argument("--execute", action="store_true"); parser.add_argument("--confirm-plan-digest")
    args = parser.parse_args(); plan = json.loads(args.dependency_plan.read_text(encoding="utf-8")); catalog = load_dependency_catalog(args.dependency_catalog)
    authorization = None
    if args.execute:
        if args.confirm_plan_digest != plan.get("dependency_plan_digest"):
            print(json.dumps({"status":"blocked", "reason_code":"confirmed_dependency_plan_digest_mismatch"}, sort_keys=True)); return 2
        authorization = authorization_for(plan, args.escrow_root, operator_confirmed=True)
    try: result = acquire_dependency_bundle(plan, catalog=catalog, escrow_root=args.escrow_root, authorization=authorization, execute=args.execute)
    except DependencyAcquisitionError as exc:
        print(json.dumps({"status":"blocked", "reason_code":exc.code}, sort_keys=True)); return 2
    print(json.dumps(result, sort_keys=True, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
