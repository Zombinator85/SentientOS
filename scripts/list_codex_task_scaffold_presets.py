from __future__ import annotations

import argparse
import json

from sentientos.codex_task_scaffold_presets import get_preset, list_preset_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.preset_id:
        preset = get_preset(args.preset_id)
        payload = {
            "preset_id": preset.preset_id,
            "default_deliverables": preset.default_deliverables,
            "default_forbidden_surfaces": preset.default_forbidden_surfaces,
            "default_integration_expectations": preset.default_integration_expectations,
            "default_validation_command_families": preset.default_validation_command_families,
            "default_final_report_items": preset.default_final_report_items,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.json:
        print(json.dumps({"preset_ids": list_preset_ids()}, indent=2, sort_keys=True))
    else:
        for preset_id in list_preset_ids():
            print(preset_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
