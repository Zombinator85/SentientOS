# Audit Process

This document outlines how the SentientOS community reviews logs and resolves concerns.

## Schedule
Audits occur monthly and whenever a security or ethics issue is raised. Rolling verification scripts (`verify_audits.py`) can be run at any time.

## Review Steps
1. Reviewers fetch the latest logs from `logs/`.
2. Each entry is hashed and compared against the manifest in `config/master_files.json`.
3. Findings and concerns are logged to `logs/audit_discussion.jsonl`.
4. Decisions are recorded with reviewer names and a SHA-256 rolling hash.

## Flagging & Resolving Issues
- Contributors may open an **Audit or Ethics Concern** issue.
- Reviewers discuss and note their resolution in the issue thread.
- Once resolved, the conclusion is appended to the audit log and linked from the issue.

## Participate
Anyone can request an audit by filing an issue or contacting maintainers listed in [CONTRIBUTORS.md](../CONTRIBUTORS.md).
