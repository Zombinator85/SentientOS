"""Read-only CLI for deterministic local runtime provisioning plans."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from sentientos.local_runtime_provisioning import environment_profile_from_mapping, observe_local_runtime_environment, plan_local_runtime_provisioning

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-plan", type=Path, required=True)
    parser.add_argument("--runtime-catalog", type=Path, required=True)
    parser.add_argument("--environment-profile", type=Path)
    args = parser.parse_args()
    selection = json.loads(args.selection_plan.read_text(encoding="utf-8"))
    catalog = json.loads(args.runtime_catalog.read_text(encoding="utf-8"))
    environment = environment_profile_from_mapping(json.loads(args.environment_profile.read_text(encoding="utf-8"))) if args.environment_profile else observe_local_runtime_environment()
    print(json.dumps(plan_local_runtime_provisioning(selection, environment, catalog), sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
