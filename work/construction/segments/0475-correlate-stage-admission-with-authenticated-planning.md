# Sequence 475 — Correlate explicit stage admission with authenticated planning

## Source increment

Starting from verified main `b69d75884bcf3e33c6a877d0bcdd454311a87f53`, this increment adds a daemon read-only projection that correlates three existing owner results: the canonical plan derived from one verified transition receipt, the campaign owner's binding of that plan to its currently active trial, and the transition controller's state-bound inspection of one explicitly supplied stage approval.

The projection returns an aligned candidate only when the request identity and in-progress trial agree, the plan digest and authenticated operator principal are present, the campaign returns a nonempty binding digest for that exact plan/principal, and the supplied approval's phase and requested stage match the canonical prior and next stages. It rereads the transition plan before returning and fails closed if it changes during inspection.

The result is informational. It does not process a request mailbox, select or mint an approval, advance the campaign, execute a stage, or grant authority. The transition request's installation-verified principal is labeled authenticated; the stage approval's origin remains explicitly unauthenticated and its owner must revalidate before execution.

## Local verification

The focused transition-composition, campaign, operator, and transition-experiment suites passed 101 tests together; the focused daemon composition file passed 15 tests. Compilation of both touched files and `git diff --check` passed. The first local iterations exposed an incomplete failure projection (`campaign_advanced` was absent) and test-double setup issues; the failure projection was made consistent and the fixtures were corrected. A final negative case confirms a plan without digest identity is rejected before campaign binding. Earlier local Mypy comparison was not source-tree-exact and is not used as a gate result; the exact-candidate hosted Mypy baseline ratchet passed.

## Hosted verification and merge

Candidate `5b52e3b943267bec02db41d526cd2976991eba82` has tree `7da13862f09ecd7e75bcbe77699d53b82f321df1` and one parent, verified main `b69d75884bcf3e33c6a877d0bcdd454311a87f53`. GitHub independently returned the candidate commit diff and recursive tree, including source blob `08e99ad4467d56511a97704defbb6e2a82b4911d` and test blob `47ace299dae4f73edd78357b3b0fc39662e81084`.

The exact-candidate Required Quality Gate #39347874691 succeeded, including hosted Administrator strict audits, immutability verification, pre-commit and landing finalizers, and the separate pre-publication metadata guard bound to head `5b52e3b943267bec02db41d526cd2976991eba82` and tree `7da13862f09ecd7e75bcbe77699d53b82f321df1`. The gate used its solo profile; exhaustive matrix execution was not requested. PR #2454 CI, Docker, Codex CI, Release, Gradient null regression, Lint Benchmark, invariants, Helm, source validation, docs, and both Quality Gate checks succeeded. Conditional welcome and publication jobs were skipped.

PR #2454 merged using the regular merge method with expected head `5b52e3b943267bec02db41d526cd2976991eba82`. Main advanced to merge commit `7cfd381c531f979a5f38277fbad1da952b8093c6`, tree `7da13862f09ecd7e75bcbe77699d53b82f321df1`, ordered parents `b69d75884bcf3e33c6a877d0bcdd454311a87f53` and `5b52e3b943267bec02db41d526cd2976991eba82`.

Post-merge Required Quality Gate #39348523496, CI #39348523276, Docker #39348523459, Codex CI #39348523405, Invariant Tests #39348523275, and Docs Deploy #39348523967 all succeeded. CI's source-validation job passed append-only custody verification, the integrated resource-to-cognition lifecycle, exact resource-to-cognition acceptance, canonical planning/execution separation, transition-stage receipt projection, and transition receipt-to-campaign planning without execution. Helm integration, self-check, Mypy baseline ratchet, pytest with coverage, Sphinx linkcheck, and container smoke/build checks passed. Forge Smoke #39348523468 was skipped by its workflow condition.

The hosted self-check provenance bound to merge commit `7cfd381c531f979a5f38277fbad1da952b8093c6` reports 143 passed, 0 failed, and 13 skipped among 156 selected tests. Its bounded selection did not include the two newly added stage-admission test cases; those cases and the 101-test affected local suite passed with the canonical `scripts.run_tests` runner against the exact touched source blobs.

## Independent operational observation

Federation Health run #39347148781 executed on pre-increment main `b69d75884bcf3e33c6a877d0bcdd454311a87f53`. Its actual hosted Administrator preflight, report generation, report binding, and artifact upload succeeded. Artifact #12231432566 binds the report hash `e16a5a4ac85b5c0f3dead86466a0fc6666b47e23b7e1bca2b0689527d0ceb3e9` to that head and run. The report reflects one configured local log node and zero events in 24 hours; it explicitly is not live federation telemetry. The separate publisher job failed because repository Actions settings do not permit the workflow token to create pull requests. This operational run predates sequence 475 and is not evidence of execution on `7cfd381c531f979a5f38277fbad1da952b8093c6`.

## Next dependency and limits

The daemon can now produce a verified, stage-aligned admission candidate while keeping both request execution and approval origin authentication separate. A useful next step is to bind this minimized verified operator provenance into immutable trial outcome evidence through the canonical campaign owner, while preserving historical outcome records and requiring live transition-owner revalidation. No production operator catalog, signing key, production request, campaign execution, or A-to-B-to-A transition was provisioned or run. Historical test provenance remains integrity-broken and sequence-286 loss remains unresolved. Stale and protected workspaces remain untouched.
