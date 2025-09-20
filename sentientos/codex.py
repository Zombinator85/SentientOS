"""Codex CLI for managing confirmation veils."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Callable

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from daemon import codex_daemon


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage Codex predictive patches that require manual confirmation."
    )
    subparsers = parser.add_subparsers(dest="command")

    confirm = subparsers.add_parser(
        "confirm", help="Apply a pending Codex veil patch and record the confirmation."
    )
    confirm.add_argument("patch_id", help="Identifier of the pending veil patch.")
    confirm.set_defaults(func=_run_confirm)

    reject = subparsers.add_parser(
        "reject", help="Reject a pending Codex veil patch and discard the diff."
    )
    reject.add_argument("patch_id", help="Identifier of the pending veil patch.")
    reject.set_defaults(func=_run_reject)

    return parser


def _run_confirm(args: argparse.Namespace) -> int:
    try:
        result = codex_daemon.confirm_veil_patch(args.patch_id)
    except Exception as exc:  # pragma: no cover - surfaced through CLI output
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_reject(args: argparse.Namespace) -> int:
    try:
        result = codex_daemon.reject_veil_patch(args.patch_id)
    except Exception as exc:  # pragma: no cover - surfaced through CLI output
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] | None = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return func(args)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
