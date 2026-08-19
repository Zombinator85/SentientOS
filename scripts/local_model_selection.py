"""Read-only local model selection review CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.host_inventory import build_host_inventory_manifest
from sentientos.local_model_selection import hardware_profile_from_inventory, plan_local_model_selection_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("host_inventory", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = json.loads(args.host_inventory.read_text(encoding="utf-8"))
    allowed = {"manifest_id", "node_id", "host_id", "os_family", "os_release", "architecture", "cpu_summary", "gpu_summary", "ram_summary", "disk_summary", "warning_risk_codes"}
    inventory = build_host_inventory_manifest(**{key: value for key, value in raw.items() if key in allowed})
    plan = plan_local_model_selection_file(hardware_profile_from_inventory(inventory), args.manifest)
    payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.write_text(payload, encoding="utf-8")
    else: print(payload, end="")
    return 0 if plan["status"] == "selected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
