"""Inspect or execute one precomposed offline runtime installation plan."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from sentientos.local_runtime_installation import InstallationError, authorization_for, install

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installation-plan", type=Path, required=True)
    parser.add_argument("--observed-environment", type=Path, required=True)
    parser.add_argument("--wheel", action="append", type=Path, default=[])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-installation-plan-digest")
    args = parser.parse_args()
    plan = json.loads(args.installation_plan.read_text(encoding="utf-8"))
    observed = json.loads(args.observed_environment.read_text(encoding="utf-8"))
    auth = None
    if args.execute:
        if args.confirm_installation_plan_digest != plan.get("installation_plan_digest"):
            print(json.dumps({"status":"blocked", "reason_code":"installation_authorization_invalid"})); return 2
        auth = authorization_for(plan, operator_confirmed=True)
    try: result = install(plan, wheel_paths=args.wheel, observed_environment=observed, authorization=auth, execute=args.execute)
    except InstallationError as exc:
        print(json.dumps({"status":"blocked", "reason_code":exc.code}, sort_keys=True)); return 2
    print(json.dumps(result, sort_keys=True, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
