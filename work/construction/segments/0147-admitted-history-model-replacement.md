# Sequence 147 — Bind model-replacement history to admitted records

Verified source commit `ce7c9fbd7536f93073b4bd2f004eb1f9f72a2369`, tree `d997a284e2c35686b5923c6fc4304f7b27a881e3`, published by expected-HEAD CAS from `87a9f8ff74ae70612774d8f1724cf364df91e397`. The branch, commit/tree, and two changed source/test blobs were independently read back.

`FrozenCausalContext.create_from_admitted_history()` now composes the existing read-only writeback inventory and retrieval APIs. It accepts only bounded unique record IDs present in the completed-record inventory, requires their verified writeback receipts to bind the same record IDs/digests, re-reads the selected records, and derives the exact ID/digest set and frozen payload from that custody. It performs no repair, writeback, cognition, model transition, or activation. Existing directly constructed contexts remain available for explicitly synthetic rehearsal compatibility.

The resource-backed parent/child integration now uses this constructor to feed the already admitted records into the A/B experiment and later cognition. An adversarial non-admitted record ID is rejected. The actual test is marked legacy by the repository; its default invocation skipped, and the correctly selected command `pytest --override-ini addopts='' -m legacy` passed: **1 passed**.

Changed Python files compiled. No mypy, hosted CI, production, or real-model validation was run. This establishes that A/B context can consume currently admitted history with exact custody, not that the models used it or improved.
