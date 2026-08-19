"""Review bounded read-only hardware facts used by local model selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from sentientos.host_collectors import (
    collect_accelerator_observation,
    collect_cpu_feature_observation,
    collect_cpu_observation,
    collect_disk_observation,
    collect_memory_observation,
    collect_platform_observation,
)
from sentientos.host_inventory import build_host_inventory_from_collector_results
from sentientos.local_model_selection import hardware_profile_from_inventory, plan_local_model_selection_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Observe local inference hardware without mutation or runtime probing.")
    parser.add_argument("--output", type=Path, help="Write canonical JSON to this path; stdout is used otherwise.")
    parser.add_argument("--manifest", type=Path, help="Optionally plan against a supplied pinned local manifest.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = (
        collect_platform_observation(), collect_cpu_observation(), collect_cpu_feature_observation(),
        collect_memory_observation(), collect_disk_observation(), collect_accelerator_observation(),
    )
    inventory = build_host_inventory_from_collector_results(results)
    profile = hardware_profile_from_inventory(inventory)
    payload = {
        "boundary": "read_only_hardware_observation",
        "inventory": inventory.to_dict(),
        "hardware_profile": profile.to_dict(),
        "selection_plan": plan_local_model_selection_file(profile, args.manifest) if args.manifest else None,
        "posture": {
            "hardware_presence_is_not_runtime_availability": True,
            "runtime_availability_is_not_commissioning": True,
            "no_network": True, "no_download": True, "no_install": True,
            "no_model_load": True, "no_commissioning": True, "no_host_mutation": True,
        },
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
