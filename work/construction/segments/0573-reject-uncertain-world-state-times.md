# Sequence 573 — reject uncertain World-State times

World-State freshness now treats RFC 3339 `-00:00` as undated because its UTC offset is unknown. The daemon validates each tick for an explicit known offset and representable epoch before cache reuse, owner reads, or board publication. Invalid ticks produce degraded non-authorizing feedback, clear the current in-memory snapshot, and do not publish a board.

PR #2609 candidate `8aaa7c0800d09f22a0a8599c66f51fdc6b431044`, based on verified main `3c28f93efe7dfbf55c16133384810abecbba23db`, used tree `fbaed7a9c453348e2a20dc7166796db21e396203`. GitHub blob and complete tree readback matched the local source and test files. The World-State suite and full resident developmental cognition suite passed locally (103 passed, 9 skipped); compilation and `git diff --check` passed.

The exact hosted candidate passed all 47 acceptance nodes, full CI and source validation, Mypy/lint, Invariants, Docker, Release, Gradient, and Codex CI. The strict Quality Gate ran under actual Administrator authority (`effective_uid=0`), verified strict audits and audit immutability without repair, preserved source identity, and passed the separate prepublication metadata guard. The solo profile did not request an exhaustive matrix.

Three exploratory neighboring embodiment tests failed locally: the inert-board assertion omitted the built-in quarantine-custody fact; a synthetic caller health assertion was expected to become current truth despite unknown freshness; and a replacement-failure monkeypatch did not accept directory-relative parameters. The same three failures reproduce on verified pre-change main tree `bb0a4401e9648c8523bdd319befe97ddfae8104e`. They are baseline test-contract issues, not regressions from this timestamp change; they are preserved for a separate test-contract repair. Hosted candidate CI and required source validation passed.

PR #2609 merged normally as `0a774ff5c9f79480e1ff7210dde81f0e26c9347c`. Its tree `fbaed7a9c453348e2a20dc7166796db21e396203` exactly matches the candidate; ordered parents are verified main `3c28f93efe7dfbf55c16133384810abecbba23db` and candidate `8aaa7c0800d09f22a0a8599c66f51fdc6b431044`. Post-merge CI, Quality Gate, Invariants, Docker, Docs Deploy, Codex CI, and Nightly Self Check passed; Forge Smoke was conditionally skipped.

At `2026-10-22T02:49:35Z`, the latest scheduled Federation Health run remained successful on ancestor source `b96d9d4da5b532ff8acf13d73d8c05d4f9316222` (run `39692862932`). No scheduled run on current main `0a774ff5c9f79480e1ff7210dde81f0e26c9347c` was observed. The report remains a stale configured local log snapshot, not live federation telemetry. No production inference or privileged operational effect was run.

Sequence: 573 (verified source integration)
