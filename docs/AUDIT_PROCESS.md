# Audit Process

This document outlines how the SentientOS community reviews logs and resolves concerns.

## Schedule
Audits occur monthly and whenever a security or ethics issue is raised. Rolling verification scripts (`verify_audits.py`) can be run at any time.

### Launching
Run `python verify_audits.py` to check all configured logs. Invalid lines are listed with their numbers and quarantined to `*.bad` files. You can generate a cleaned copy using `python cleanup_audit.py <log>`.

### Review
1. Inspect any `.bad` files and attempt recovery.
2. Commit the cleaned log and rerun the verifier.

## Review Steps
1. Reviewers fetch the latest logs from `logs/`.
2. Each entry is hashed and compared against the manifest in `config/master_files.json`.
3. Findings and concerns are logged to `logs/audit_discussion.jsonl`.
4. Decisions are recorded with reviewer names and a SHA-256 rolling hash.

## Maintaining the Log Manifest
The file `config/master_files.json` lists every immutable log tracked by the
project.  Whenever you create a new audit log or repair an existing one, run
`sha256sum <file>` and update the corresponding digest in this manifest.  The
`verify_audits.py` script reads this list by default, so the hashes must match
the current file contents.

## Flagging & Resolving Issues
- Contributors may open an **Audit or Ethics Concern** issue.
- Reviewers discuss and note their resolution in the issue thread.
- Once resolved, the conclusion is appended to the audit log and linked from the issue.

If `verify_audits.py` reports a broken chain, pause commits and create an **Audit or Ethics Concern** issue. Include the `.bad` file and any recovered entries so maintainers can reconstruct the log.

## Participate
Anyone can request an audit by filing an issue or contacting maintainers listed in [CONTRIBUTORS.md](../CONTRIBUTORS.md).

### Sample Audit Recovery Report
```
Audit recovery 2025-09
Log: logs/example.jsonl
Recovered: 98%
Lines needing review: 2 (lines 45, 46)
Chain status: valid after cleanup
Reviewer sign-off: carol
```

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
