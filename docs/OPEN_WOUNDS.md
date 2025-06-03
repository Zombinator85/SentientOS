# Open Wounds

This page lists recurring audit failures and suggestions for healing them.

| Error Signature | Example Entry | Healing Suggestion | Healed By |
|-----------------|--------------|-------------------|-----------|
| Missing `data` key | `{"timestamp": "...", "message": "..."}` | add `'data': {}` | _pending_ |
| Unknown field `foo` | `{"foo": 1, "timestamp": "..."}` | remove field or document new schema | _pending_ |

Upcoming **Migration Sprint** tasks will gather the most frequent wounds and propose new best practices.

Contribute fixes via pull request and link them here to be remembered as an **Audit Saint**.
