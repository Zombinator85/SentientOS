# Sequence 490 — fail closed when daemon planning observes model drift

## Identity drift regression

PR #2481 extends the recovered positive history integration test over two planning ticks. It first confirms the exact bound model can use the supported experience. On the next tick the read only serving identity observer returns a different model. The goal is then deferred with `epistemic_applicability_unresolved`; the persisted positive state identity and current verified posture remain visible in the allocation artifact, and no empty work plan is fabricated.

The recovered epistemic owner remains unchanged. The test continues to forbid session acquisition, inference, executor calls, and work run artifacts. Test only; no runtime behavior or authority changed.

## Verification and merge

Candidate `71b3ef8064a5521cede91a49a8fc2e2799932913` (tree `71872aa0a18ac80af1648e5358d0af0d855583c8`) was based on verified main `405f620e06285d99f81fdaa1189bd8df443d9320`. The affected planning, staging, progression, daemon integration, persistence, and history suite passed 66 tests: 62 passed, 4 existing skips, zero failures. Compilation passed. Mypy matched 1,050 baseline diagnostics, retired 40, and added zero.

Exact candidate Quality Gate #39387847033 passed with hosted Administrator authority, strict audits, audit immutability, exact acceptance, and the separate pre publication metadata guard. All PR and push checks passed. PR #2481 was merged by regular merge as `d7db09da4567f2977575a17d3356dc0ac128fab2`, tree `71872aa0a18ac80af1648e5358d0af0d855583c8`, with ordered parents `405f620e06285d99f81fdaa1189bd8df443d9320` and `71b3ef8064a5521cede91a49a8fc2e2799932913`. GitHub reports a valid signature; independent main readback confirmed the changed test blob exactly matches the candidate.

Post merge Quality Gate, CI, Codex CI, Docker, Docs Deploy, and invariants passed on the merge SHA. Forge Smoke was skipped by workflow condition.

## Next dependency

Expose the already bound target model identity digest and observation time in compact daemon planning feedback. Verify these fields explain the model bound selection and drift deferral without exposing raw identity or adding authority.
