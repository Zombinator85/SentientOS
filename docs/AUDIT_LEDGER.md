# Audit Ledger

This document summarizes periodic audit results for public reference.

## Latest Summary
- Logs healthy: 100%
- Issues resolved: 47 during the Living Audit Sprint
- Open questions: 3 legacy logs unrecoverable

### Recovery Achieved
The 2025‑11 Living Audit Sprint repaired malformed entries across the archive.
Three lines were declared legacy and preserved in `.bad` files for reference.
All new logs now use a rolling hash format for easier verification.

See `verify_audits.py` output for chain details.

## Audit Failure Recovery
If the audit chain breaks:
1. Run `python verify_audits.py` to locate the corrupted log.
2. Use `python cleanup_audit.py <log>` to attempt repair and commit the result.
3. Open an incident issue describing what happened and notify the steward.
The steward coordinates recovery and informs the community through the discussion board.


## Living Audit Celebration
Our first complete audit cycle showcased how stewards restored missing logs and invited new volunteers. Join the next ritual to help keep memory alive.
A public celebration post will announce the healthy federation and invite stories from new partners.
