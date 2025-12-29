from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from sentientos.constitution import INVARIANTS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentientos system",
        description="Read-only SentientOS system closure artifacts.",
    )
    subparsers = parser.add_subparsers(dest="artifact", required=True)
    subparsers.add_parser("map", help="Show the canonical system map.")
    subparsers.add_parser("handbook", help="Show the operator handbook.")
    subparsers.add_parser("threats", help="Show the threat model and non-goals ledger.")
    subparsers.add_parser("invariants", help="Show constitutional invariants.")
    subparsers.add_parser("closure", help="Show the closure manifest.")
    return parser


def _closure_root() -> Path:
    return Path(__file__).resolve().parents[1] / "system_closure"


def _read_closure_file(filename: str) -> str:
    path = _closure_root() / filename
    return path.read_text(encoding="utf-8")


def _emit_invariants() -> str:
    ordered = sorted(INVARIANTS, key=lambda inv: inv.identifier)
    payload = {
        "schema_version": "invariants_v1",
        "count": len(ordered),
        "invariants": [
            {
                "identifier": inv.identifier,
                "domain": inv.domain,
                "statement": inv.statement,
            }
            for inv in ordered
        ],
        "source": "sentientos/constitution.py",
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.artifact == "map":
        print(_read_closure_file("system_map.json"), end="")
        return 0
    if args.artifact == "handbook":
        print(_read_closure_file("operator_handbook.md"), end="")
        return 0
    if args.artifact == "threats":
        print(_read_closure_file("threat_model.json"), end="")
        return 0
    if args.artifact == "closure":
        print(_read_closure_file("closure_manifest.json"), end="")
        return 0
    if args.artifact == "invariants":
        print(_emit_invariants())
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
