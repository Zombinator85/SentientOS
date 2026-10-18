# Active construction checkpoint

Latest verified `main`: `3696b2aeb9fab43629cf037fc7337db0d0d2b0a9`, tree `0b698550ca6bfb9786f55e4d3c0515cafec8f3c1`. PR #2340 merged normally with both parents preserved. Candidate CI, QG, Docker, invariants, Codex CI, lint, Release, and Gradient passed. Post-merge CI, privileged QG, Docker, invariants, Codex CI, Docs Deploy, and feedback passed; QG independently confirms 29/29, UID 0, exact source/tree, clean strict and immutability audits, and source unchanged. Forge Smoke was skipped by workflow conditions.

Sequences 349–350 fix and verify the hosted CI race in the synthetic chat-process handoff child. It now mirrors production's bounded retry for only the unpublished handoff condition, then verifies lineage. The repair changes tests only; no serving behavior or authority changed. Local affected suites passed 38 tests with one pre-existing legacy skip, and the formerly failing node passed 20 consecutive runs.

Operational evidence remains pending: as of 2026-10-18 04:26 UTC, no scheduled Federation Health, Nightly Audit Integrity, or Nightly Self Check run is available on this main. Latest observed runs remain `39083395122` on `7d19f2651e8b09bd614322a1ba4ad8b2ae014218`, `39014123936` on `50d062baab7f838b1dfeaf9b79ec42c5da0e0a14`, and `38876666946` on `d8d7a219221cd94240accf7991fe353b14f6a84e`. The workflows preserve strict Administrator calls and least-write scopes. The GitHub connector cannot dispatch workflows; a manual Federation Health run with `publication_fixture=false` is needed for current-source hosted execution. The changed-output fixture remains separate and unrun. Preserve sequence-286 provenance-loss evidence and the stale sequence-178 workspace.

Latest construction segment: `work/construction/segments/0350-merge-and-verify-handoff-fixture-repair.md`
Latest segment SHA-256: `e4628361c101cc099a39b96c9450c58dbdb03bb659954b6381b85e60751cd785`
Sequence: 350
