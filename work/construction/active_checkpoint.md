# Active construction checkpoint

Sequence 315 improved read-only transition status with the canonical recovery reason, outstanding stage, replay-forbidden flag, and semantically verified journal-entry digests. The exact acceptance test passed and proves that status inspection advances no stage and appends nothing. No recovery effect, retry, token reconstruction, or authority was added.

Latest source-bearing main commit: 4d5c8347a1687f7faeedabdf3006df8140ba146a
Verified source tree: b7eca92c69ba32f05fc3d3b2c4cc4ecbb9ddc459
Latest construction segment: work/construction/segments/0315-expose-transition-recovery-status.md
Sequence: 315
Latest segment SHA-256: 40ff4399de4cabe29f13807466c06c1d476c9cec25253c9c89032a5cf6fc0984

The Federation Health changed-output fixture still needs an explicit workflow_dispatch through the GitHub Actions UI; this connector exposes no dispatch action. Production temporal A→B→A remains unexecuted pending exact commissioned setup and an operator-approved protocol. Status now provides safer diagnostics, but automatic reconciliation of an interrupted stage remains unsafe without independent operator evidence.

Sequence 286’s nine known and one unidentified unrecoverable payloads remain unresolved. The stale sequence-178 workspace remains untouched.
