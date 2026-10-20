# Active construction checkpoint

Sequence 497 records PR #2494's regression for interrupted persisted plan evidence binding. Both the external sidecar-only state and complete evidence envelope require an explicitly supplied expected evidence digest before execution can create task effects, journals, or run artifacts. The partial sidecar is preserved on rejection.

Latest source-bearing main commit: `50c1d9ab99d8d81b0a28ba58185c8a99349b17ca`
Verified source tree: `03da01b4f4d39d592c32d210f3bed990a609dd4a`
Latest construction segment: `work/construction/segments/0497-partial-plan-evidence-sidecar-fail-closed.md`
Latest segment SHA-256: `3089ccefcb21807d423255a7bce19f1e5300849d5010d921c742803887de8699`
Sequence: 497

The PR's affected suite passed 85 tests. Exact-candidate hosted CI, Required Quality Gate (including hosted strict audits, finalizer, and separate metadata guard), invariants, Gradient, Codex CI, Release, Docker, and Lint passed. The solo profile did not request an exhaustive matrix. No production task, inference, campaign, or transition execution occurred. Continue the bounded retained-experience to canonical decision path while preserving planning/execution separation and authority boundaries.
