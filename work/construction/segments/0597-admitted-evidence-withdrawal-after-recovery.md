# Sequence 597 — admitted withdrawal removes active evidence after recovery

PR #2651 closes the evidence-free withdrawal validation gap. Sequence 596 had shown that an `evidence_withdrawal` update can withdraw a supported conclusion by returning its stance to unknown, but its test retained the binding in the active state set. This increment now proves actual governed binding removal.

The resident mutation controller already computes removed-binding deltas from the candidate's complete active evidence set and records them in the append-only update event. The blocker was the candidate factory's blanket rejection of empty evidence IDs. The factory now permits an empty set only when the reason is `evidence_withdrawal` and the proposed stance is `unknown`. It continues to reject evidence-free new-evidence updates and positive withdrawals.

The end-to-end test admits withdrawal of the exact proposition's active support and contradiction, reconstructs the owner and controller, and confirms the active set remains empty while all three immutable binding records remain present. Canonical planning stays review-required and creates no work run. The focused candidate regression verifies the narrow validator exception. No model inference or execution occurs.

The correction to sequence 596 is recorded here without altering its append-only segment: the controller did support admitted removals; only the candidate-shape guard prevented an all-bindings withdrawal.

The exact source candidate is `27b19e9fbe04511eb08b7dcd181b9b8f72af7804`, tree `bcc756e3b122780a7b1bf091dcbd926c869ad125`, based on verified main `658826d834c2b7c9852bdde8109685b80bdf1a44`. Python syntax compilation passed locally. Hosted pytest with coverage, the mypy baseline ratchet, lint matrices, source validation, and integrated resource-to-cognition lifecycle all passed.

All eight exact-candidate workflows passed: CI 39877485700, Required Quality Gate 39877485795, Release 39877485513, Codex CI 39877485661, Gradient null regression 39877485949, Invariant Tests 39877485951, Docker Image 39877485813, and Lint Benchmark 39877485705. The strict gate passed actual Administrator audits, exact acceptance binding, audit immutability, hosted finalization, and the separate metadata guard.

PR #2651 merged normally as `b58b2d96c72ecaa048221d383f7c3fa0b3d06d04`. Its tree is `bcc756e3b122780a7b1bf091dcbd926c869ad125`, identical to the candidate tree, with verified main `658826d834c2b7c9852bdde8109685b80bdf1a44` as first parent. No production authority or execution behavior was expanded.

Sequence: 597 (verified source integration)
