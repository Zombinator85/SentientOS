# Sequence 571 — reject uncertain canonical planning times

Canonical `plan_goals` now rejects RFC 3339 `-00:00`, which means an unknown local offset rather than UTC, before resolving the repository or inspecting the verified epistemic owner. When prior history is configured, Unix timestamp conversion failures become `planning_time_unrepresentable` before repository/history reads. The computed projection tick and validated state bound are carried into the single owner read; canonical planning remains read-only and never invokes goal execution.

Two regressions prove rejection order: an unknown offset and a platform timestamp overflow both fail before repository graph access or owner projection. The full focused canonical planning suite passed 16 cases through `scripts.run_tests`; modified files compiled; `git diff --check` passed. Pinned Mypy 1.20.2 reported zero new errors and 40 retired against the unchanged baseline.

PR #2605 candidate `a543193a7df3b9465600773a854672ad0ae7e4eb`, based on verified main `c8453166d7a0806c0e02ae3030d378d4ca4cbff0`, used tree `f3d3baa4fb6361adabb633f352266228b2f127be`. Candidate CI, source validation, self-check, docs, Docker, Release, Invariants, Lint Benchmark, Gradient, Codex CI, and strict Required Quality Gate passed. Exact-candidate acceptance binds all 47 required nodes to the candidate; hosted privileged finalization required strict audits and immutable-audit verification, disallowed audit repair, and passed the separate pre-publication metadata guard.

PR #2605 merged normally as `7f22bd2157dfd0549f33eecf74a74fce56c8352c`, preserving verified main as first parent and the candidate as second. The merge tree equals the candidate tree. Post-merge CI, Quality Gate, Invariants, Docker, Docs Deploy, and Codex CI passed; Forge Smoke was conditionally skipped. Source validation passed the integrated resource-to-cognition lifecycle and the transition receipt, planning, and execution separation acceptance nodes.

The latest scheduled Federation Health run remains bound to ancestor source `b96d9d4da5b532ff8acf13d73d8c05d4f9316222`; no scheduled run on main `7f22bd2157dfd0549f33eecf74a74fce56c8352c` was visible at 2026-10-22 01:42:41 UTC. The report from the older run describes a stale local snapshot and is not live federation telemetry. The two nightly workflow contracts remain correctly scoped and their latest scheduled executions succeeded on older source commits; no workflow change was justified.

No production model inference or privileged operational effect was run.

Sequence: 571 (verified source integration)
