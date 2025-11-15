from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sentientos.runtime import bootstrap
from sentientos.runtime.shell import RuntimeShell, load_or_init_config


def _resolve_config_path() -> Path:
    base_dir = bootstrap.get_base_dir()
    config_dir = base_dir / "sentientos_data" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "runtime.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sentientos.cathedral")
    subparsers = parser.add_subparsers(dest="command")

    rollback_parser = subparsers.add_parser(
        "rollback", help="Revert a previously applied amendment by id"
    )
    rollback_parser.add_argument("amendment_id", help="The amendment identifier to revert")

    args = parser.parse_args(argv)

    if args.command == "rollback":
        config_path = _resolve_config_path()
        config = load_or_init_config(config_path)
        shell = RuntimeShell(config)
        try:
            result = shell.rollback(args.amendment_id, reason="Manual rollback via CLI")
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"Rollback failed: {exc}", file=sys.stderr)
            return 1
        if result.status in {"success", "partial"}:
            print("Rollback complete.")
            return 0
        if result.status == "not_found":
            print("Rollback metadata not found.", file=sys.stderr)
            return 2
        print("Rollback failed — see logs for details.", file=sys.stderr)
        return 3

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
