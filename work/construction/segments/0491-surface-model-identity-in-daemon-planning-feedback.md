# Sequence 491 — surface model identity context in daemon planning feedback

## Feedback traceability increment

PR #2482 adds the target model identity digest and its observation time to canonical daemon planning feedback. These values were already bound into allocation artifacts and, when a plan exists, its evidence. The feedback now gives operators the same model context without exposing the raw identity.

The integrated regression verifies that a current supported position is selected at its exact model identity, then remains visible but is deferred after the observer reports a different model. It checks the changed model digest and planning tick in daemon feedback, unresolved applicability in the allocation artifact, unchanged recovered state, no serving session or model invocation, no execution, no authority, and no work run artifact. The source change is limited to the feedback fields and focused tests.

## Verification and merge

Candidate `e26d85082c19b9c5ced1bc924ece184556883602` (tree `00d600c2cb55c41e3829b9cba02efb4c821ff87b`) was based on verified main `d7db09da4567f2977575a17d3356dc0ac128fab2`. The affected planning, staging, progression, daemon integration, persistence, and history suite passed 66 tests: 62 passed, 4 existing skips, zero failures. Compilation passed. Mypy matched 1,050 baseline diagnostics, retired 40, and added zero.

Exact candidate Quality Gate #39388875162 passed with hosted Administrator authority, strict audits, audit immutability, exact acceptance, and the separate pre publication metadata guard. All PR and push checks passed. PR #2482 was merged by regular merge as `6046002357a51cf5f96fa5ec4b067155b3024040`, tree `00d600c2cb55c41e3829b9cba02efb4c821ff87b`, with ordered parents `d7db09da4567f2977575a17d3356dc0ac128fab2` and `e26d85082c19b9c5ced1bc924ece184556883602`. GitHub reports a valid signature; independent main readback confirmed both changed source blobs exactly match the candidate.

Post merge Quality Gate, CI, Codex CI, Docker, Docs Deploy, and invariants passed on the merge SHA. Forge Smoke was skipped by workflow condition.

## Next dependency

Verify a scheduled Federation Health execution against an integrated main head, and continue tracing model bound historical evidence through read only daemon feedback and persisted allocation evidence. Nightly audit and self check schedules remain independent hosted verification requirements; no current head scheduled result is claimed here.
