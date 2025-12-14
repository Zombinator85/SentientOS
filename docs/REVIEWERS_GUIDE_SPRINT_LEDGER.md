# Reviewer's Guide to Sprint Ledgers

This one-page reference explains how to read the healing sprint dashboard and verify metrics.

## Dashboard Overview
- Run `python healing_sprint_ledger.py` to update `docs/SPRINT_LEDGER.md`.
- The ledger lists healed log counts, new contributors, remaining integrity issues, and federation nodes.

## Verifying Metrics
1. Review `AUDIT_LOG_FIXES.md` for repaired line counts.
2. Run `python collect_schema_integrity issues.py` to confirm open integrity issues.
3. Inspect `logs/federation_log.jsonl` for unique peers.
4. Compare entries in `logs/contributor_stories.jsonl` with the **Contributor Stories** section.

## Reading Contributor Stories
Each bullet in the ledger comes from the `contributor_stories.jsonl` log. These short notes prove active community care. Federated nodes are invited to open a pull request adding their metrics and stories for inclusion.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
