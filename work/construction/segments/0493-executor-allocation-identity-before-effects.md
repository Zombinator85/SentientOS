# Sequence 493 — enforce allocation identity at execution

## Executor boundary

PR #2488 carried the canonical plan's allocation path and content digest into ExecutorState, then checked those values against the persisted evidence binding before opening the execution journal or invoking tasks. Replaced allocation bytes, a mismatched path, or a stale digest fail closed. The existing bounded execution authority checks remain in place.

The affected local executor, CLI, orchestration, and evidence-bound suites passed 46 tests; compilation and diff checks passed. Hosted candidate Quality Gate, Administrator audit, immutability, acceptance, and repository checks passed. PR #2488 was merged with history preserved as 0f735ff5eb2fddee934f220aec4262beb3d1cb86, tree 87ae91ae4c3ad9d3ffcfc46a1a838bdc75c0397b, from candidate 634fb566840e2470866eaab289ba2035ac3665c7.

A subsequent source-callsite audit found that the canonical CLI still supplied manual identity values. That integration defect was repaired and verified in sequence 495 before recording the end-to-end allocation-binding dependency as complete.

## Limits

No production task, inference, campaign, or transition was executed.
