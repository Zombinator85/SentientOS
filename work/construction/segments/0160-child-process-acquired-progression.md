# Sequence 160 — Reconstruct acquired progression in a child process

**Source:** `dffb2a4ed3d3d90abc79dc73e32b561424ef93b1`  
**Tree:** `6bd53110703169a5a25489bfd0586b7c55611130`

The three-episode acquired-history fixture now serializes only fixture-issued invocation receipts, starts a fresh Python child, and reconstructs the progression through the normal durable admission/history/experiment owners. The child reproduces exact task-family record and digest attribution plus per-episode score contrasts without inheriting the parent owner or invoker objects. Existing bounded report recovery also uses the same child-process helper.

The positive three-episode reconstruction and generic bounded-recovery case passed (**2 passed in 69.48s**); changed Python tests compiled. This verifies fixture custody and no-replay semantics, not real model operation.

Next: inspect remaining oracle and source-provenance boundaries in the task-family record, then run focused tampering cases against the exact upstream task instance, evaluated output, and selected history binding.
