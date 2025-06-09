from __future__ import annotations

from admin_utils import require_admin_banner, require_lumos_approval
import argparse
import os
import sys

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

# Backwards compatibility wrapper around the new audit_chain module.

from audit_chain import AuditEntry, append_entry, read_entries, verify, _hash_entry


def cli() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--no-emoji", action="store_true", help="disable emoji output")
    args, unknown = parser.parse_known_args()
    if args.no_emoji:
        os.environ["SENTIENTOS_NO_EMOJI"] = "1"

    require_admin_banner()
    from audit_chain import cli as _cli

    sys.argv = [sys.argv[0], *unknown]
    _cli()


if __name__ == "__main__":  # pragma: no cover
    cli()
