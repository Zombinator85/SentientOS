# 0373 — Bind resource-owner failure and recovery to tick boundaries

## Regression finding and proof

The sequence-372 per-tick cache also stores an owner read failure so downstream projections cannot silently retry the owner within the same tick. Sequence 373 adds an adversarial regression proving this boundary. A transient first read yields no resource World-State fact and no `causal_resources` projection; both report the same failed-read outcome, while the owner call count stays at one. The next tick performs one new read, and both projections expose the same installation identity and manifest digest.

No source runtime behavior changed in this sequence. The regression protects the failure path of the existing read-only observation cache and does not create model, mutation, execution, or authority effects.

## Verified source and hosted merge

Source is exact main merge `fa8a934ed34bb50b0988aeb0fd829a8806d132f8`, tree `a67c9c115990317c79e98f6edb5ae619e2d6cb25`. PR #2362 candidate `09417da4c869233587c3640f24a9378376b6a294` passed Required Quality Gate (hosted Administrator strict audit and landing finalizer included), CI, Docker, Invariants, Gradient, Codex CI, Lint Benchmark, and Release. The regular merge completed successfully. All six changed blob IDs were read back through the GitHub main branch file API and matched the candidate tree.

Post-merge checks are **unobserved**: the available GitHub connector returns only pull-request-triggered commit workflow runs, returned none for the merge commit, and reported no simple commit statuses. A direct read-only API request was blocked by the sandbox proxy. No post-merge green result is claimed.

## Verification

`python -m scripts.run_tests -q sentientos/tests/test_resource_observation_world_state_integration.py tests/test_sentientosd_causal_introspection_composition.py tests/test_sentientosd_runtime_closure.py tests/test_host_resource_runtime.py tests/test_production_chat_resource_observation_recovery.py tests/test_causal_introspection.py`: 82 passed, 0 skipped. The mypy baseline reported zero new errors and 40 retired error records. `py_compile`, `git diff --check`, and continuation custody verification passed.

## Custody

Evidence JSON: `work/construction/evidence/0373-bind-resource-read-failure-to-tick.json`

Evidence SHA-256: `7ced4eab090ebdd654cd99f44f38602123fe621965f9820dc6aaedd122240b1d`

Source baseline: `fa8a934ed34bb50b0988aeb0fd829a8806d132f8` (tree `a67c9c115990317c79e98f6edb5ae619e2d6cb25`).

Predecessor: `segment-sha256:eb93ff0ed9d9d31cc4556ab814ecb380d5d3362cf003d81bbf500fdd966d476c`
