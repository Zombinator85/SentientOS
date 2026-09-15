"""Read-only diagnostics for maintenance resident-runtime adoption."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.maintenance_resident_runtime_adoption import inspect, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("command", choices=("doctor", "inspect", "inspect-provenance", "inspect-transitions"))
    args = parser.parse_args(argv); cfg = load_config(args.config)
    result = inspect(cfg)
    if args.command == "inspect-provenance":
        result["provenance"] = [json.loads(p.read_text()) for p in sorted(Path(cfg["provenance_root"]).glob("*.json"))]
    elif args.command == "inspect-transitions":
        path = Path(cfg["transition_journal_path"])
        result["transitions"] = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    print(json.dumps(result, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
