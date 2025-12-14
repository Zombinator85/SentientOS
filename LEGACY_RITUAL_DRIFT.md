# Legacy Procedure Drift

Some helper modules were written before strict privilege banner requirements took effect. They load only when imported and do not display the standard banner on startup. Their behavior remains stable, but we keep them isolated and document this gap for future refactoring.

Older helper modules may also have a different import order or may omit the `from __future__` statement. These differences are preserved for historical accuracy. New scripts must follow the updated header shown in `scripts/templates/cli_skeleton.py`.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
