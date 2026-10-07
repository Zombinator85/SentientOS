from __future__ import annotations
from audit_chain import AuditEntry, append_entry, read_entries, verify, _hash_entry
# Backwards compatibility wrapper around the new audit_chain module.



def cli() -> None:
    from sentientos.privilege import require_admin_banner, require_lumos_approval

    require_admin_banner()
    require_lumos_approval()
    from audit_chain import cli as _cli

    _cli()


if __name__ == "__main__":  # pragma: no cover
    cli()
