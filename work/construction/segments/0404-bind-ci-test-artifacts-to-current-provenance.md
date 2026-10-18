# Sequence 404: bind uploaded test artifacts to the current provenance

The sequence-403 merge is now fully verified on main `e53c3219c431c9c11de6bf40a764d3913fba1f57` (tree `30075ab4c789356cb647dcc528845af06db4c030`). Its post-merge Required Quality Gate, CI, Docker, invariants, Docs Deploy, and Codex CI all passed. Forge Smoke was skipped by its configured opt-in condition.

Inspection of the current-main CI artifacts showed that the upload wildcard `pytest_junitxml*.xml` included tracked XML reports from historical test runs, including stale failures beside provenance for the current successful run. That made the artifact ambiguous even when the hosted self-check itself passed. This increment stages only the JUnit report and failure digest named by `test_run_provenance.json`. It checks that provenance belongs to `GITHUB_SHA`, was written after a per-job cutoff marker, and references files inside `glow/test_runs/` with the expected names. A manifest records the provenance hash, source SHA, run identity, artifact hashes, and sizes. Old staged outputs are removed from the isolated runner temporary directory before each copy. Both source-validation and self-check use the same helper, and source-validation explicitly runs its safety tests.

The new tests cover exact current-report staging, stale-output removal, path containment, provenance freshness and source matching, malformed provenance, and CI step ordering. In a clean local source worktree at commit `fd2221cf8fdcfc125b349b633efec6ddd0ea8a7b`, tree `c080840587cdcd9516eebb0e83a2c6501ef4312e`, the canonical runner completed 44/44 selected tests with zero skips or failures. The Mypy baseline comparison reported zero new errors and status `mypy_baseline_improved`; compilation, diff checks, and strict custody verification of all 403 existing sequences passed. Exact runner provenance and the JUnit report are retained in this evidence record. GitHub-hosted checks against the final candidate remain the source-bound acceptance gate.

The change only copies read-only test artifacts into the per-job temporary directory for upload. It adds no repository write privilege, runtime authority, provider call, inference, or production effect.

Latest construction segment: `work/construction/segments/0404-bind-ci-test-artifacts-to-current-provenance.md`
Latest segment SHA-256 is bound in the append-only construction index.
Sequence: 404 (local targeted tests and source checks passed; hosted exact-candidate verification pending)
