from __future__ import annotations
import argparse
from pathlib import Path
import sys

from sentientos.household_presence_sensor_inventory import (
    build_default_inventory,
    dumps_inventory_json,
    inventory_result_to_dict,
    validate_inventory_contains_known_surfaces,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("build-default", "inspect-repo", "validate", "summarize"))
    p.add_argument("--workspace-root", default=".")
    p.add_argument("--input")
    p.add_argument("--output")
    p.add_argument("--summary", action="store_true")
    a = p.parse_args(argv)
    result = build_default_inventory(a.workspace_root)

    if a.command in {"build-default", "inspect-repo"}:
        text = dumps_inventory_json(result)
        if a.output:
            Path(a.output).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    if a.command == "validate":
        ok, missing = validate_inventory_contains_known_surfaces(result)
        if not ok:
            print("missing:" + ",".join(missing), file=sys.stderr)
            return 2
        print("inventory_valid")
        return 0
    summary = inventory_result_to_dict(result)
    print(f"status={summary['status']} surfaces={len(summary['surfaces'])} warnings={len(summary['warnings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
