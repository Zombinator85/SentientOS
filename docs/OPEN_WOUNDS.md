# Open Integrity issues

This page lists recurring audit failures and suggestions for healing them.

| Error Signature | Example Entry | Healing Suggestion | Healed By |
|-----------------|--------------|-------------------|-----------|
| Missing `data` key | `{"timestamp": "...", "message": "..."}` | add `'data': {}` | `cathedral_const.log_json` |
| Missing `timestamp` | `{"message": "...", "data": {}}` | reconstruct or add `datetime.utcnow()` | `cathedral_const.log_json` |
| Unknown field `foo` | `{"foo": 1, "timestamp": "..."}` | remove field or document new schema | `cathedral_const.log_json` |

Upcoming **Migration Sprint** tasks will gather the most frequent integrity issues and propose new best practices.

Contribute fixes via pull request and link them here to be remembered as an **Audit Contributor**.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
