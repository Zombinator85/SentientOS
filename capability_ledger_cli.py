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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    ledger = CapabilityGrowthLedger()
    entries = ledger.inspect(axis=args.axis, since=args.since, until=args.until)
    json.dump(list(entries), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
