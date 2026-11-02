"""Read-only validation and readiness commands for companion deployment manifests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from sentientos.gaming_companion_deployment import inspect_local, validate_manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "doctor"):
        item = subparsers.add_parser(command)
        item.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        path = Path(args.manifest)
        if path.is_symlink() or not path.is_file():
            raise ValueError("manifest_path_unsafe_or_missing")
        value: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("manifest_not_object")
        if args.command == "validate":
            validate_manifest(value)
            result = {
                "schema_version": "sentientos.gaming_companion_readiness:v1",
                "status": "manifest_validated",
                "host_mutation_performed": False,
            }
        else:
            result = inspect_local(value)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {
            "schema_version": "sentientos.gaming_companion_readiness:v1",
            "status": "blocked",
            "reason_codes": [str(exc)],
            "host_mutation_performed": False,
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") in {"manifest_validated", "ready", "ready_with_warnings"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
