# Active construction checkpoint

Sequence 324 adds Linux process start-time identity to maintenance-resident child launch provenance. Recovery distinguishes an old child from a new process that reused its PID only when procfs start time differs. Same-generation, unknown, and legacy-but-present cases remain fail-closed. No signaling, adoption, or transition-replay authority is added.

Construction source is verified main `8a2ab13333574d9112442ef826351596077f267a`, tree `3c0470660da9fd2daeb2a7ffe8b9d83cf82d38c7`. The starting blobs for both changed source files were read from that exact tree. The isolated local source projection omitted runtime state and audit data; it is not represented as a full-repository checkout.

Local compilation and diff checks passed. The canonical local test runner stopped before pytest because its airlock found `jinja2` unavailable; dependency installation is blocked by sandbox network policy. No local test pass is claimed. Exact regression nodes are recorded in the acceptance manifest; hosted CI and the strict hosted Quality Gate are pending.

Sequence 323 merged as PR #2322, merge commit `8a2ab13333574d9112442ef826351596077f267a`, tree `3c0470660da9fd2daeb2a7ffe8b9d83cf82d38c7`. Current-main Quality Gate, CI, Codex CI, invariants, Docker, and Docs Deploy passed (runs 39073711468, 39073711486, 39073711461, 39073711497, 39073711558, and 39073711583). Dependabot Graph Update run 39073716852 remains in progress at checkpoint preparation.

Federation Health's latest scheduled success is run 39065143484 on source `b91969c1b1a900fefe102fb72697e7295766857b` (sequence 318 evidence): 1 node, 0 recent events, quiet; publisher operation none. No scheduled run on current main `8a2ab13333574d9112442ef826351596077f267a` is observed yet. The latest scheduled execution remains distinct from the changed-output test fixture, which cannot be dispatched through the available GitHub connection.

The nightly workflows currently retain Administrator verification through `sudo`; only the audit repair job holds content and PR write permission. No exact-current-main scheduled execution is observed. No unnecessary workflow permission change was made.

The sequence-323 narrative says 9 local dependency tests, but its retained provenance artifact records 10 passed, 0 failed, and 0 skipped (SHA-256 `3ef05a5e67ffb4016b096e65929fad25a47cae0729f99f0bd3ef2ce6fb54ecaf`). This discrepancy is corrected in sequence 324 without rewriting prior evidence.

Outstanding limitations: the exact commissioned A-to-B-to-A production campaign remains unexecuted; process-generation identity does not prove detached descendants or inference workers have terminated. Sequence-286 payload loss remains unresolved. The original Vow salt-key bytes remain unrecovered, with no replacement or rotation. The stale sequence-178 workspace remains untouched.

Latest construction segment: `work/construction/segments/0324-bind-resident-child-recovery-to-process-generation.md`
Sequence: 324
Segment SHA-256: e44d6f808a6826ec8ee1392e4ad7c416855eee42262e4556622e65f81ef008da
