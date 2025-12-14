# Log Directory
This folder contains the audit logs used by SentientOS. All files are JSONL and verified with `verify_audits.py`.

- `federation_log.jsonl` — active federation events, audit chain intact.
- `privileged_audit.jsonl` — privileged action ledger, audit chain intact.
- `migration_ledger.jsonl` — legacy migration notes with a preserved `prev hash` mismatch; blessed as historical evidence, not for repair.
- `support_log.jsonl` — legacy support messages with one `prev hash` mismatch; also blessed as historical evidence.

These mismatched entries document the project’s evolution and will never be rewritten.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
