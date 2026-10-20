# Sequence 495 — bind canonical CLI execution to persisted plan identity

## Close the executor integration path

After sequence 493 added a fail-closed executor check, scripts/work_plan_run.py still passed the manual graph and allocation identity for canonical plans. Valid plans loaded by this CLI were therefore rejected by the new binding. PR #2490 now takes the graph hash, allocation artifact path, and optional allocation digest from the already verified persisted evidence and supplies them to ExecutorState. Manual plans retain their manual identity. The regression persists the exact allocation artifact and asserts that the CLI forwards the verified identity and evidence digest while preserving the integrity-pressure mutation boundary.

The affected local CLI, executor, orchestration plan-only, and evidence-bounds suites passed 49 tests; compilation and diff checks passed. The exact candidate was 95bc0b67237abaa69fdb0377c546b615c121356f, tree 60e57156e3aa646e4aa1610db4fee934e97d3be1, based on main 0ac5125cafd104df0b72d40207bae19eecf6faba. Hosted Quality Gate run 39404380102 passed its strict Administrator audits, acceptance, privileged finalizer, and separate pre-publication metadata guard. The downloaded finalizer artifact's bytes matched GitHub's SHA-256 digest; the guard bound the candidate head and tree and returned pr_metadata_guard_ready. CI 39404380101, Docker 39404380315, Lint Benchmark 39404380230, Invariant Tests 39404380272, Codex CI 39404380081, Release 39404380247, and Gradient null regression 39404380054 all passed on the exact candidate, including docs linkcheck, full self-check, source validation, and Helm.

PR #2490 was merged without squashing or rebasing as 54c9764b6726a46e6f7d667232e726ba2795007a; its ordered history preserves the candidate and its parent main. The remote main readback contains the exact verified source and regression-test blobs: scripts/work_plan_run.py 2854b4a0c2e12145b5b8ec9830d810b840734948; sentientos/tests/test_work_plan_cli.py 6fd5e130b839e020120e5d1d928643475e941fb3. The resulting main tree is 60e57156e3aa646e4aa1610db4fee934e97d3be1.

## Limits

No production task, inference, campaign, or transition was executed. A scheduled Federation Health run on the new main head has not yet been independently observed; the available workflow-run listing connector filters to pull-request-triggered runs.
