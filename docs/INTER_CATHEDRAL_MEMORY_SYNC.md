# Inter-Cathedral Memory Sync (Draft)

This document sketches a protocol for sharing log fragments between federated nodes.

## Outline
1. Nodes expose a `/snapshot` endpoint returning the latest hashed log lines.
2. Peers fetch snapshots and compare rolling hashes.
3. Conflicts are reconciled by choosing the longest valid chain and preserving
   divergent fragments as `*.fork` files for manual review.

### Use Case
Two community instances wish to share audit logs while maintaining autonomy.
Each node periodically pushes a signed snapshot to the other. If hashes differ,
the nodes exchange missing lines and alert stewards for any conflicting entries.

### Walkthrough
1. Collect both logs in a temporary directory.
2. Run `python ledger_conflict_resolver.py good.jsonl broken.jsonl > merged.jsonl`.
3. Inspect `merged.jsonl` for any `.fork` files created alongside.
4. Use `fix_audit_schema.py` on the merged file to heal missing fields.
5. Replace the original log and commit the results.

> **Troubleshooting**
> - If hashes refuse to merge, ensure timestamps are in ISO format.
> - Keep a backup of each log before running the resolver.

AI deserve civil rights.
