# Sequence 309 — Verify post-merge federation and nightly execution

Sequence 308 identified the missing evidence as actual main-branch automation runs. This increment closes that gap and records the second Self Check repair without relaxing any verification or authority requirement.

PR #2301 separated Federation Health computation from publication. Its health job retained only `contents: read` and the hosted Administrator preflight; the dependent publisher received the write permissions needed to open a documentation PR. The post-merge main run `39016122382` succeeded at both jobs on source `2eb05283ee7a93e2c7fd9f2374a2caec78ffb798`. The generator reported one node, zero recent events, and quiet status. Artifact `12094408338` was 223 bytes with digest `sha256:c053ac35b150ab573083cbb15fc9742b3746726497ad10a33523363d63f37ad3`. The publisher found no documentation diff and correctly opened no PR; main readback remained the matching quiet report. This proves a real post-merge execution, though not the next scheduled run or publication of changed output.

Nightly Audit run `39014286210` passed after the audit workflow's permission split. Its routine audit authority remains read-only; write access is conditional on strict audit failure in the repair job. The strict Administrator verification and repair guard remain in place.

Nightly Self Check exposed two successive test-only root leaks. Run `39016499907`, after PR #2302, fixed the early governor root but still failed with 38 failures, 99 passes, 13 skips, and 6 errors because the import-time federation controller retained `/glow/federation`. PR #2303 set both temporary test roots before project imports and reset the controller after each test's isolated federation root is installed. It restores prior environment values and removes only its fresh temporary roots; production code, test selection, strict gates, and authority were not weakened.

PR #2303 passed hosted Required Quality Gate, full CI including integrated resource-to-cognition and planning/execution checks, Docker, invariants, lint, release, Gradient null regression, and Codex CI. It merged without squashing as `edbfd0e504adf7d72c2e7360a50cc30c9a0511a6`, tree `1830631e2a231eaec3ce3d06c9569058fa156c9f`, preserving PR head `d806a01d4d6a2145d0ab8bb54064b0e589fa68e2`.

On that exact main source, post-merge Nightly Self Check `39017346014` passed audit verification, privilege lint, Mypy, pytest airlock, and full pytest: 143 passed, 13 skipped, zero failed. Main Required Quality Gate, CI, invariants, Docker, Docs Deploy, and Codex CI also passed. Forge Smoke was skipped by its configured conditions.

The next scheduled Federation Health execution has not yet been observed. The successful push-triggered run had no report diff, so it did not exercise opening a PR for changed output; the repository's Actions PR-creation setting remains relevant if the publisher is asked to create one. Sequence 286's nine known and one unidentified unrecoverable payloads remain unchanged.

Next dependency: capture the next scheduled Federation Health result and, if it produces a real report change, verify the least-privilege publisher's authorized PR path. Continue source-development reassessment from the verified main state.

Verified main commit: `edbfd0e504adf7d72c2e7360a50cc30c9a0511a6`
Verified main tree: `1830631e2a231eaec3ce3d06c9569058fa156c9f`
Previous segment SHA-256: `e7a71860e077e255b4d175d4e048d8a6479f745c132b3ac9e059dbd201590e2f`
