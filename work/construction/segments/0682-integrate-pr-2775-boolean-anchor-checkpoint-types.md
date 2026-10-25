# Sequence 682: integrate PR 2775 and verify boolean byte-count custody

PR #2775 merged normally as `adfd97d8ec513ffdb0916ca74e76146eaf55f88e` from candidate `134c5ad1a4e5ec926ff697ed3f3a43f551921463`; the verified merge tree `9140d73da9e839a61f50bbb94bf6e20bb509d12b` matches its final candidate tree. The change makes construction custody reject boolean legacy-journal and segment byte counts and adds regression coverage at both custody verification and candidate publication. The published v2 continuation now verifies through sequence 681.

All eight applicable exact-head PR workflows passed: Required Quality Gate, CI, Release, Gradient null regression, Codex CI, Invariant Tests, Docker Image, and Lint Benchmark. All applicable post-merge workflows passed: Required Quality Gate, CI including source validation/self-check/docs/linkcheck/Helm, Docs Deploy, Invariant Tests, Codex CI, Nightly Self Check, and Docker Image. Forge Smoke was skipped by workflow condition.

The focused construction custody/publication suite passed 43/43. Mypy baseline reported zero new errors with overall improvement. Every one of the eight candidate blobs read back exactly and candidate source preflight reported `candidate_integrity_ready_for_ref_update`. The frozen v1 index/checkpoint and all earlier v2 shards remain unchanged.
