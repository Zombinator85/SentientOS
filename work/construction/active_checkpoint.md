# Active construction checkpoint

## Current verified state — sequence 594

Sequences 591–593 carry receipt-verified outcomes into planning and bind the resulting plan identity to execution. Sequence 594 verifies that this rationale survives persisted plan evidence reload with its allocation digest intact, and that a support binding owned by a different proposition is rejected. The regression preserves restart verification and planning/execution separation.

Latest verified main: `c79b84f7fcaf1ab484cd7157f61666edf9016e45`, tree `4231ebb733ed10ebdffeb573670197e3e7c90b45`
Latest construction segment: `work/construction/segments/0594-reload-plan-evidence-preserves-proposition-scope.md`
Latest segment SHA-256: a907a00fbda14eee93c5f6e085e9fde23b6248ff11099e4a20ff584a2e593bc5
Sequence: 594 (verified source integration)

Next: extend the negative evidence-substitution proof through durable recovery. Verify that a rejected foreign-proposition binding leaves no proposition state transition or mutation receipt, while the authority ledger remains auditable; then test stale or withdrawn supporting bindings against canonical planning after restart. Preserve the exact plan/allocation binding, evidence custody, and no-execution boundary.
