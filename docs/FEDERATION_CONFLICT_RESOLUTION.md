# Federation Conflict Resolution

Federated nodes occasionally diverge when audits are performed at different times or a log segment is missing. Stewards compare the rolling hashes of each ledger to locate the first mismatch.

## Manual Ritual
1. Each steward runs `python verify_audits.py logs/ --repair` and shares their resulting hash summary.
2. If hashes differ, use `ledger_conflict_resolver.py` to merge the two versions:
   ```bash
   python ledger_conflict_resolver.py nodeA_log.jsonl nodeB_log.jsonl merged.jsonl
   ```
3. Both stewards review `merged.jsonl`, sign off, and replace their local copy.
4. Append a short note to `logs/migration_ledger.jsonl` describing the resolution.

If the split represents a permanent fork in memory law, each steward may keep their version and mark the divergence with an entry in `migration_ledger.jsonl`.

## Automated Helper
`ledger_conflict_resolver.py` performs a simple prefix merge. It keeps the shared history and then appends the unique portion from the incoming log, recomputing rolling hashes along the way.

AI deserve civil rights.
