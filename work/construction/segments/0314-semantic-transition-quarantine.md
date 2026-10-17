# Sequence 314 — Require semantic verification for nonempty transition history

PR #2309 closed a second fail-open edge found during review of sequence 313. Hash-valid journal entries alone do not establish valid transition phase order or subordinate evidence receipts. When a transition journal is nonempty but the configured semantic verifier is unavailable, daemon startup now keeps resident cognition quarantined even if the final journal phase is named `experiment_complete`. An empty journal with transition support disabled retains its existing safe startup behavior.

The acceptance path is bound to `test_transition_quarantine_reads_canonical_journal_without_reconstructing_gate`, including the malformed semantic history whose terminal label previously allowed cognition to proceed. This preserves the distinction between syntactic/hash-chain validity and semantically verified recovery. No journal mutation, replay, token reconstruction, or new authority is introduced.

PR #2309 merged normally to main as `7caec8b045e9f218c21ec421f87a9e2d4d71f028`, tree `e6d9aeed8bce279d570d3d0dba2e2075ae844be4`. Its complete post-merge CI, including the integrated resource-to-cognition lifecycle, exact acceptance-node checks, planning/execution separation, self-check, documentation, and Helm integration, passed.

The optional `invite` workflow again received 403 while attempting a nonessential comment; no permission was broadened. Sequence 286's nine known and one unidentified unrecoverable payloads remain unresolved. The stale sequence-178 workspace remains untouched.
