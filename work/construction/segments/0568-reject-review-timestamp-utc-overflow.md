# Sequence 568 — reject review timestamp UTC overflow

The five context-hygiene review timestamp parsers now map UTC normalization overflow to invalid review time. Negative regressions cover both representable-range edges in each of `reviewed_at`, `evaluated_at`, and `expires_at`, asserting that malformed receipts never satisfy their future gate. The canonical local runner passed all five affected receipt suites; compilation and `git diff --check` passed. Repository Mypy reported zero new errors and 40 retired baseline errors.

PR #2600 candidate `b4e8371d120ef431e99a135fc4ad28ddd62cdcc8`, tree `0c93ad3a2d664b84f2f92fc8e4b39e3e8310c966`, was based on verified main `67bd7199cb62fdf4fc04a6ed750653f54672bcd5`. Its hosted CI, build, Helm/Kubernetes, docs/linkcheck, self-check, invariants, lint, Docker, Release, Codex CI, and Gradient checks passed. The strict hosted Quality Gate ran with actual Administrator authority; all 47 exact call-phase nodes passed, the separate pre-publication metadata guard reported `pr_metadata_guard_ready`, and the hosted landing finalizer bound the candidate SHA and tree. Artifacts were retained by GitHub.

PR #2600 merged normally as `6f75aece49019d0a0f417cca78cc1f8192de3f96`, preserving the candidate tree and ordered parents (`67bd7199cb62fdf4fc04a6ed750653f54672bcd5`, then `b4e8371d120ef431e99a135fc4ad28ddd62cdcc8`). Exact-main CI, Quality Gate, Invariants, Docker, Docs Deploy, Codex CI, and Nightly Self Check passed. Forge Smoke was conditionally skipped. Source validation also passed the exact outcome-to-planning and planning/execution-separation nodes.

No production inference or model transition was run. The independent scheduled Federation Health report still describes a stale local snapshot, not live telemetry.

Sequence: 568 (verified source integration)
