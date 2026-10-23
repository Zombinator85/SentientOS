# Active construction checkpoint

## Current verified state — sequence 596

Sequences 591–593 connect receipt-verified outcomes to canonical planning and bind plan identity to execution. Sequence 594 verifies durable planning evidence reload and rejects foreign-proposition support. Sequence 595 proves rejected cross-proposition evidence leaves no target mutation intent or receipt. Sequence 596 verifies that stale-only support and an admitted withdrawal of the supported conclusion remain review-required after restart, while current exact-scope support restores planning eligibility.

Latest verified main: `76c93596d4d714594d9dcac246e86f6943b015af`, tree `c334e2c0a225843910f1c8cb406b607d667fce0d`
Latest construction segment: `work/construction/segments/0596-recovered-planning-freshness-and-withdrawal.md`
Latest segment SHA-256: 373300160452d8bd65d1d6a694c1399c379b5b7e4951d7a0c6e8113f148bc2af
Sequence: 596 (verified source integration)

Next: trace how immutable evidence bindings are withdrawn and superseded across the state owner, mutation controller, admission evidence, and canonical projection. The owner supports removed-binding deltas, but the resident mutation controller exposes no governed removal path. Implement and test the narrowest authority-bound removal operation, preserve the append-only binding record and update history, and prove a withdrawn binding cannot restore favorable planning posture after restart. Keep planning non-executing.
