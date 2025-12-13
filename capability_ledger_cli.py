from __future__ import annotations

import argparse
import json
import sys

from capability_ledger import CapabilityAxis, CapabilityGrowthLedger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="capability-ledger",
        description="Read-only inspection for the Capability Growth Ledger.",
    )
    parser.add_argument(
        "--axis",
        choices=[axis.value for axis in CapabilityAxis],
        help="Filter entries by capability axis (R, C, E, or K).",
    )
    parser.add_argument(
        "--since",
        help="Return entries recorded at or after this ISO 8601 timestamp.",
    )
    parser.add_argument(
        "--until",
        help="Return entries recorded at or before this ISO 8601 timestamp.",
    )
    parser.add_argument(
        "--version-id",
        help="Filter entries by recorded version identifier.",
    )
    parser.add_argument(
        "--git-commit",
        help="Filter entries by recorded git commit hash.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "jsonl"],
        default="json",
        help="Choose between JSON array output or newline-delimited JSON (JSONL).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    ledger = CapabilityGrowthLedger()
    # Boundary assertion: CLI exports are audit artifacts only; do not treat
    # them as optimization signals, planning inputs, or prompt material.
    entries = ledger.inspect(
        axis=args.axis,
        since=args.since,
        until=args.until,
        version_id=args.version_id,
        git_commit=args.git_commit,
    )
    if args.format == "jsonl":
        for entry in entries:
            sys.stdout.write(json.dumps(entry, separators=(",", ":")))
            sys.stdout.write("\n")
    else:
        sys.stdout.write(json.dumps(list(entries), separators=(",", ":")))
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
