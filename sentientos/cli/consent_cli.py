from __future__ import annotations

import argparse
import json
from typing import Iterable

from sentientos.embodiment.consent import ConsentLedger, OperatorRole
from sentientos.embodiment.contracts import SignalType


def _parse_signal_types(values: Iterable[str]) -> tuple[SignalType, ...]:
    signal_types: list[SignalType] = []
    for value in values:
        try:
            signal_types.append(SignalType(value))
        except ValueError:
            raise argparse.ArgumentTypeError(f"unsupported signal type: {value}")
    return tuple(signal_types)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consent contract simulation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    grant = subparsers.add_parser("grant", help="Grant a consent contract (simulation only).")
    grant.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in OperatorRole],
        help="Operator role required for the scope.",
    )
    grant.add_argument(
        "--signal-type",
        required=True,
        nargs="+",
        help="Signal types covered by this consent contract.",
    )
    grant.add_argument(
        "--context",
        required=True,
        help="Context label for the consent scope (e.g. cli, simulation).",
    )
    grant.add_argument(
        "--duration",
        type=int,
        required=True,
        help="Duration in seconds for this consent contract.",
    )

    revoke = subparsers.add_parser("revoke", help="Revoke a consent contract by id.")
    revoke.add_argument("contract_id", help="Consent contract id to revoke.")
    revoke.add_argument("--reason", help="Reason for revocation.")

    list_parser = subparsers.add_parser("list", help="List consent contracts.")
    list_parser.add_argument(
        "--active-only",
        action="store_true",
        help="List only active consent contracts.",
    )

    return parser


def _emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _grant(args: argparse.Namespace) -> int:
    signal_types = _parse_signal_types(args.signal_type)
    ledger = ConsentLedger()
    contract = ledger.grant_contract(
        operator_role=OperatorRole(args.role),
        signal_types=signal_types,
        context=str(args.context),
        duration_seconds=int(args.duration),
    )
    _emit_json({"status": "granted", "contract": contract.to_dict()})
    return 0


def _revoke(args: argparse.Namespace) -> int:
    ledger = ConsentLedger()
    entry = ledger.revoke_contract(args.contract_id, reason=args.reason)
    _emit_json({"status": "revoked", "entry": entry})
    return 0


def _list(args: argparse.Namespace) -> int:
    ledger = ConsentLedger()
    records = ledger.list_records()
    if args.active_only:
        records = [record for record in records if record.status == "active"]
    _emit_json([record.to_dict() for record in records])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "grant":
        return _grant(args)
    if args.command == "revoke":
        return _revoke(args)
    if args.command == "list":
        return _list(args)
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI invocation
    raise SystemExit(main())
