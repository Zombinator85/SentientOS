# Sequence 589 — reject duplicate epistemic transaction records

PR #2634 adds an exact source-validation regression for an authentic admission-bound state transaction copied byte-for-byte to a second path in the transaction collection. The duplicate has private file mode but a noncanonical filename. Reconstruction rejects it at collection identity validation before recovery, and the test confirms state, update events, both transaction files, the published state receipt, and admission records remain unchanged.

The candidate is a verified descendant of PR #2633's sequence 588 evidence. PR #2633's own CI self-check remained in progress at integration on its FFmpeg demo-export step. The descendant included that full evidence tree and passed the complete exact-candidate checks, providing an independent full CI run for both increments.

Candidate `8149e053a07e83f635638a477eda2f43101dd346` passed all eight hosted workflows. CI run 39841676200 reported 143 passed, 13 skipped, zero failed; source validation reported 414 passed, 18 skipped, zero failed and selected both the transaction-conflict and duplicate-record regressions. Strict Quality Gate run 39841675516 passed Administrator audits, audit immutability, hosted finalization, and the separate metadata guard. Lint Benchmark, Codex CI, Gradient, Release, Invariants, and Docker also passed. Source-validation checkout `867c8301121f9ec662b876587e5a32b02a28ec76` has an identical tree to the candidate.

PR #2634 merged normally as `605712b0dcca29cb916f2508e02d7cbe0eaaeb89`; GitHub's candidate-to-merge comparison showed no file differences. Its tree is `24d0ba08983bb996e9e1a799babfe61ebde40907`. PR #2633, carrying sequence 588's evidence, was merged through this verified descendant at the same merge commit.

No inference or production transition occurred.

Sequence: 589 (verified source integration)