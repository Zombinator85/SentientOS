# Active construction checkpoint

Latest verified `main`: `ebbaa6fa447f30f9ef6bd9254c853d64149bec88`, tree `f6f9d59be414e149577e937694e777af60f3be6d`. Sequence 340 merged normally by PR #2330 with both parents preserved. Candidate CI and lint/Mypy, Docker, invariants, Release, Gradient, Codex CI, and strict Administrator QG passed. Post-merge CI, QG (29/29 exact tests, UID 0 strict/immutability clean), Docker, invariants, Codex CI, and Docs Deploy passed; Forge Smoke was skipped by its configured condition.

Sequence 340 requires both transition roles to use the same frozen model-replacement protocol and validates the complete resident history manifest against its records. Selected model-context history must match exact resident IDs/digests. No running-software observation or transition authority is implied.

A scheduled Federation Health execution, run `39083395122`, succeeded on `7d19f2651e8b09bd614322a1ba4ad8b2ae014218`, which was main at the time. Its hosted Administrator preflight and update passed; the generated report matched `docs/FEDERATION_HEALTH.md` exactly (one node, zero recent events, quiet). The publication job succeeded with no changed-output PR; changed-output fixture steps were skipped. This establishes scheduled execution, not changed-output publication.

Next source dependency: expose a deterministic count and canonical digest for omitted resident history, after exact frozen selection integrity and boundary receipt validation. Sequence 341 is open as draft PR #2331; hosted CI and privileged QG are pending. Keep the current Nightly Audit and Nightly Self Check privilege requirements and least-write scopes. Their next scheduled executions on `ebbaa6fa447f30f9ef6bd9254c853d64149bec88` have not yet occurred.

Preserve sequence 286 provenance-loss evidence and the stale sequence-178 workspace. Fixture and hosted CI evidence do not establish production developmental evidence.

Latest construction segment: `work/construction/segments/0340-verify-transition-protocol-and-history-boundary.md`
Latest segment SHA-256: `4c2f5db6b868006c0581e2ef5dd9007574bd37b6622b14e6306b75d3bc73b9eb`
Sequence: 340
