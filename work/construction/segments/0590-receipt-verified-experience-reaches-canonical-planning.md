# Sequence 590 — receipt-verified experience reaches canonical planning

PR #2636 adds an exact-source regression that exercises the complete durable lineage from an authority-admitted epistemic update through restart recovery into the daemon's canonical planner. Before the update, the goal is selected. After writing a real mutation receipt, a newly constructed owner fails closed with `epistemic_mutation_lineage_unverified` until the mutation controller re-verifies receipt custody. Once verified, the retained unknown position causes the planner to defer the goal with `epistemic_review_required`. The test patches execution to fail if planning calls it and confirms no work plan is produced.

The candidate `bde315c91b6e04684a3a1aaaed0f488db164e7db` passed all eight exact-candidate hosted workflows. CI run 39843776113 passed the full self-check suite (143 passed, 13 skipped, zero failed); the targeted canonical-planning and execution-separation acceptance node and source validation also passed. Required Quality Gate run 39843776147 passed strict Administrator audits, audit immutability, hosted finalization, and the separate metadata guard. Lint Benchmark (39843776287), Release (39843776228), Invariant Tests (39843776115), Gradient null regression (39843776164), Codex CI (39843776018), and Docker (39843776422) passed.

PR #2636 merged with a normal merge commit as `3266bc6a352ab515d9e29fe149ee64b21240a773`. The merge retained candidate tree `a3c46f657313ab958438580ad3badde29f9a77d8`; candidate-to-merge comparison reported no file changes. The preceding source commit was `bde315c91b6e04684a3a1aaaed0f488db164e7db`, based on sequence 589 main `681c35a9bdff0835e038640fbac050fff9973314`.

The regression establishes that durable, receipt-verified experience can change canonical goal selection after restart, while unverified history remains unusable and planning remains non-executing. No inference or production transition occurred.

Sequence: 590 (verified source integration)
