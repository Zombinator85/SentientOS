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
