from __future__ import annotations

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

# Backwards compatibility wrapper around the new audit_chain module.

from audit_chain import AuditEntry, append_entry, read_entries, verify, _hash_entry


def cli() -> None:
    require_admin_banner()
    from audit_chain import cli as _cli

    _cli()


if __name__ == "__main__":  # pragma: no cover
    cli()
