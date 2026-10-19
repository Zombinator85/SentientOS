# Active construction checkpoint

## Latest verified main

PR #2392 regular-merged sequence 422 at main `00cedf9c46a24c268a6867d80c2a3f04da6a05c2`, with the candidate preserved as its second parent after `0722b49e30758834e4fc921c60970fe5079e6d3e`. Remote comparison found zero changed files from candidate `52849d21adf8e675f6671a256f0a0faedf772d3b`; the main tree is the candidate tree `2bfdb289021e00e9f14449a6c938b45dfe7b9703`.

The exact candidate's PR CI, Required Quality Gate, Docker, invariants, Codex CI, lint, gradient regression, and release validation passed. The separate metadata guard and landing gate passed. Hosted candidate source validation recorded 20/20 tests; Quality Gate recorded Administrator UID 0, strict audit and immutability pass, source unchanged, and acceptance 29/29. Post-merge main push checks on exact SHA `00cedf9c46a24c268a6867d80c2a3f04da6a05c2` also passed: CI #39203567028, Required Quality Gate #39203566922, Docker #39203567090, Invariant Tests #39203567041, Codex CI #39203566935, and Docs Deploy #39203566933. Forge Smoke #39203567110 was skipped by condition.

## Current work

Sequence 423 preserves the regular merge lineage and exact candidate tree. Its branch-push CI #39204028840, Required Quality Gate #39204028812, and Invariant Tests #39204028809 succeeded; the hosted pre-publication metadata guard reported `pr_metadata_guard_ready`. This evidence checkpoint is still an unmerged branch.

Sequence 424 is published as candidate `266a9a99da41abb0f30c983ec46aa675c6d83bc6` / tree `38124ee137974910354e1a1f9e38a9a68db6368e`. Its exact hosted CI, invariant, and Required Quality Gate checks are running; the new acceptance node passed within the hosted Quality Gate call phase. Finalizer and metadata guard are still in progress. Local YAML parsing, direct contract assertions, compilation, custody, and diff checks passed; the canonical pytest wrapper could not bootstrap offline.

PR #2393 carries sequence 424 and is open; its PR-event checks are still in progress.

Sequence 425 is an **untested source candidate** based on sequence 424. Its hosted Quality Gate and invariants passed; its full source-validation run failed one stale contract assertion after the intentional main guards were added. Sequence 426 updates that assertion without weakening it. It binds the audit-baseline writer, Forge Smoke, and secret-bearing Remote Smoke dispatch to main, and separates read-only baseline capture from the optional main-only write job. The existing exact acceptance node now covers these protections; the required node count is unchanged. Local YAML parsing, direct contract assertions, compilation, custody, and diff checks passed. Hosted verification is pending.

## Scheduled workflow evidence

As of 2026-10-19 05:38:47 UTC, no post-merge Federation Health scheduled run or artifact has been observed. A manual dispatch attempt through the local CLI was blocked because its GH_TOKEN is invalid; the connector exposes read-only Actions access. The result remains pending, not failed. Nightly Audit Integrity and Nightly Self Check have not run on this main; their next UTC slots are 2026-10-20 03:41 and 04:37. Current workflows retain `sudo -n`; audit repair alone has contents/pull-requests write authority, and self-check remains read-only. The latest historical scheduled outcomes remain documented in sequence 422.

## Open evidence boundaries

- Historical test provenance remains `INTEGRITY_BROKEN` at its unanchored start, including the preserved sequence-286 loss.
- No production resident A→B→A trial or inference occurred. Commissioned identities, distinct serving approvals, and operator preregistration remain required.
- Sequences 382–386 and all prior indexed records remain preserved. Stale sequence-178, sequence-411, and sequence-417 workspaces remain untouched.
- No production authority or workflow privilege changed.

Latest verified main: `00cedf9c46a24c268a6867d80c2a3f04da6a05c2`, tree `2bfdb289021e00e9f14449a6c938b45dfe7b9703`.
Latest construction segment: `work/construction/segments/0426-align-smoke-workflow-contract-with-main-guards.md`
Latest segment SHA-256: 145e1eb2e4925a17930358123be29d5bbc086b0d27d523332766fc22ddf6007a
Sequence: 426 (untested source candidate; hosted validation pending)


## Sequence 424 candidate

Branch candidate based on sequence 423 SHA `53ba18b4d810510da93a12e30f4e2435d1078be7`, tree `26d88c5f0f3727d9ae02c1db8652a2ff5ef52c7d`. Exact hosted checks are pending. Local source identity matches the base candidate; static workflow assertions, compilation, and diff hygiene passed; canonical pytest could not bootstrap offline. The append-only record does not claim the changes are merged or verified.


## Sequence 425 candidate

Branch work continues from sequence 424 `266a9a99da41abb0f30c983ec46aa675c6d83bc6` / tree `38124ee137974910354e1a1f9e38a9a68db6368e`. This candidate is unverified and is not claimed merged. It preserves the exact source lineage and does not alter the earlier sequence-423 branch.


## Sequence 426 candidate

Repair candidate based on sequence 425 `770cafd84e585924992043f204b1e3c7cd602479` / tree `d159be57eca8fa584addc3d2fed5c783ef21a56b`. It updates only the existing workflow-contract test to reflect the main guards. Hosted validation is pending.
