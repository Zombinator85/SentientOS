# Sequence 426 — Align smoke-workflow contract with main guards

**Construction status: untested source candidate.** This increment repairs a source-caused CI assertion failure discovered on sequence 425.

The sequence-425 source-validation run failed one existing workflow contract test: `tests/test_github_hosted_acceptance_workflows.py::test_smoke_job_conditions_use_supported_explicit_opt_in_contexts`. It still expected the old opt-in-only Forge and Remote Smoke conditions. Sequence 425 correctly added a `refs/heads/main` restriction to both jobs, so the stale test expectation rejected the newly required safety condition. The hosted run reported 380 passed and one failed test on source `770cafd84e585924992043f204b1e3c7cd602479` / tree `d159be57eca8fa584addc3d2fed5c783ef21a56b`.

This increment updates that existing test to assert the full main-and-opt-in conditions for both jobs. It does not relax the assertion, skip tests, or change the source workflow behavior. The required Quality Gate already passed on sequence 425 with the unchanged 30-node acceptance set, actual Administrator strict audit and immutability, and `pr_metadata_guard_ready`; the failure was in full CI's broader source-validation suite.

The direct smoke-job condition test and main-bound workflow contract test passed; YAML parsing, Python compilation, custody verification (426 segments), and `git diff --check` also passed. Canonical pytest could not be run locally because the sandbox cannot access the package index. Hosted verification of this repaired candidate remains pending. Sequence 425 and its failed test evidence remain preserved on their original branch. No main merge or post-merge Federation Health run is claimed.
