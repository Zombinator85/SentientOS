# Sequence 496 — require persisted plan evidence digest before execution

## Close the direct executor omission path

Canonical daemon and CLI callers already pass a digest for persisted plan evidence. A direct GoalExecutor caller could omit it and still execute a plan when that plan's evidence envelope existed. The executor now detects the plan-keyed evidence envelope or external-binding sidecar and rejects a missing digest before opening the journal or invoking tasks. Manual plans without persisted evidence retain their existing behavior. The regression verifies that no task, journal, or run artifact is created on rejection.

The affected executor, CLI, evidence bounds, journal, plan loading, and orchestration suites passed locally (84 tests); compilation and diff checks passed. On exact candidate a6f6c1eee0bfc8021fc08168662dc050802f0b7a (tree d268c38ca20262fcc14702ebbff11e33b10faa26, based on main 76d71080ba6545dc399f9c392b30e3a7e6e46ebf), Quality Gate run 39407788516 and CI run 39407788458 passed. The hosted Administrator audits, precommit and acceptance, privileged landing finalizer, and separate PR metadata guard passed. The guard bound candidate head a6f6c1eee0bfc8021fc08168662dc050802f0b7a and tree d268c38ca20262fcc14702ebbff11e33b10faa26 and returned pr_metadata_guard_ready. Docker 39407788449, Invariant Tests 39407788453, Gradient null regression 39407788596, Codex CI 39407788621, Release 39407788455, and Lint Benchmark 39407788439 also passed.

PR #2492 was merged with commit history preserved as 020ee1a135f013aa3b395d6f3fd69b5775e5a4ca. Remote main readback matched the exact candidate blobs: sentientos/goal_executor.py c85b156d463e566f47e8bb86b55c4f313eb0fba0; sentientos/tests/test_goal_executor_run.py 59241fd641123f70c33971047f950c3ea1becbb2. Main now contains the verified candidate tree d268c38ca20262fcc14702ebbff11e33b10faa26.

## Limits

No production task, inference, campaign, or transition was executed. The hosted validation profile was solo; exhaustive matrix output was not requested by that profile.
