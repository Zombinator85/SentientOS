"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from audit_chain import AuditEntry, append_entry, read_entries, verify, _hash_entry
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

# Backwards compatibility wrapper around the new audit_chain module.



def cli() -> None:
    from audit_chain import cli as _cli

    _cli()


if __name__ == "__main__":  # pragma: no cover
    cli()
