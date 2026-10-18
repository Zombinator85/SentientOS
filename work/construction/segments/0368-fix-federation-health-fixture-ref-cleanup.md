# 0368 — Fix Federation Health fixture ref cleanup and prove fail-closed behavior

## Why this increment exists

Sequence 367 made the sentinel branch trigger observable. The next real fixture execution (#39119356695) passed its exact branch, parent, path, and content validation, then exposed two distinct publication blockers. GitHub Actions could not create a pull request because the repository setting disallows that capability. Independently, the workflow's cleanup DELETE used the singular Git ref lookup endpoint, so ref cleanup could not succeed even if publication were enabled. The failed run's artifact remains explicitly unverified; this increment does not relabel it as success.

## Bounded repair

The publisher now keeps the singular `/git/ref/heads/…` route for GET/readback and uses `/git/refs/heads/…` for DELETE for both the run-specific output branch and the one-shot trigger branch. Cleanup exceptions include API response detail and preserve the existing fail-closed proof semantics. No workflow permission was broadened. A regression test executes the embedded cleanup program against a stateful fake GitHub CLI, proves the two successful DELETE routes and post-delete readbacks, and verifies denied cleanup remains unverified with the denial surfaced.

## Verification and limits

The canonical workflow-contract test file passed 36/36 (zero skips). YAML parsing, embedded Python AST parsing, Python compilation, and `git diff --check` passed. The final local run was on the synthetic workspace identity recorded in the evidence, so it is not treated as exact candidate verification. Candidate hosted checks must bind the exact source before merge.

The source fix cannot itself change the repository's Actions setting. The fixture remains unproven until that setting is enabled and a new hosted fixture run demonstrates changed-output PR scope, closure without merge, and verified cleanup. The failed fixture's two branches are recorded for later safe cleanup. Exact-main scheduled Federation Health evidence is still pending; the successful post-merge push run is not substituted for a scheduled event. Production A→B→A remains externally gated, and no production inference was initiated.

## Evidence custody

Evidence JSON: `work/construction/evidence/0368-fix-federation-health-fixture-ref-cleanup.json`

Evidence SHA-256: `b11d1f4785b01566476871bc1e26e11c297d93c335e895d8e72897c73b57e5cc`

Source baseline: `ef0b3fb8c4ee83d5532582fb4035d1c177f4e404` (tree `2420ed1b738f504fe6bbee3ea325f732432e8e5c`). Source SHA-256 values, hosted failure facts, all runner attempts and artifact hashes, and exact test-state cleanup are bound in the evidence JSON.

Predecessor: `segment-sha256:fd476e38bc3feca7db19d7271949c25ad0372eb29fba9f6c1b7ffbfce0ebbaa8`
