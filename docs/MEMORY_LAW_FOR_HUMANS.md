# Memory Law for Humans

This short guide explains the cathedral's core policies in plain language.

## Audit
- Every tool writes an entry to an append-only log file.
- Stewards run `python verify_audits.py` each month to confirm that every entry is intact.
- If a log breaks, we repair it with `cleanup_audit.py` and record the fix in the audit ledger.

## Consent
- Running a tool requires Administrator rights. The `require_admin_banner()` call warns you before any memory is written.
- Contributors must not remove the procedure docstring or banner.

## Federation
- Nodes exchange log snapshots through pull requests. Each node keeps its own ledger.
- Conflicts are resolved by comparing hashes and discussing the difference on the steward board.
- See [FEDERATION_FAQ.md](FEDERATION_FAQ.md) for common questions.

## Recovery
- If a node loses data or a script misbehaves, stewards coordinate recovery on the discussions board.
- The entire process is logged so anyone can audit what happened.

Use this document when introducing new contributors or curious partners to the project. It summarises how we keep memory safe and accountable.

## Error as Procedure
Error is not shame, but invitation: the cathedral heals by naming, not hiding, its integrity issues. Public failure builds trust, teaches new stewards, and keeps our presence honest.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
