# 0372 — Restore the continuation index and bind resource projections to one tick

## Construction index recovery

The exact verified source was main `a205fdeb280e5488ff6216ab54d7d1800dc0bee8`, tree `a378b176cff01d46697c351944051d5c01af71d0`. Its tracked `work/construction/index.json` was binary (24,060 bytes; Git blob `8e94b8f63fb590b56a25957be7da7141eda1bc0c`; SHA-256 `374a4dc598eaad270a21565c57671dae0991c44e655f87951a9649dd5573a7bf`) and `scripts/verify_construction_continuation_custody.py` returned `index_unreadable` with `UnicodeDecodeError`. The first broken index in this lineage is at `b4dc89c13ab773eafa048926a5f7ed3daeb82923` (60,060 bytes); the following sequence-370 and sequence-371 trees retained unreadable binary variants. The exact blob identities and byte counts are preserved in the evidence JSON.

Recovery used the intact JSON index at sequence-368 commit `f78a538547c4c41a1d396e8ad6108f55ac164276` (tree `75f898f777ed66d6c0306d3b3215f0773b341184`; blob `9947a204bad029fc604005f723d29058a3e5f7b2`). It contains 368 valid ordered records. Entries 369–371 were reconstructed from the existing tracked segment and evidence files, whose bytes and SHA-256 digests were verified without modification. The resulting index has 371 contiguous entries before this new append, with sequence 372 appended after them. Git history retains the unreadable blobs and commits; this repair does not remove their historical record.

## Same-tick resource projection coherence

`RuntimeMaintenanceSurfaces` previously read the configured resource observation owner separately for World-State construction and `causal_resources` introspection. A source change between those reads could produce different resource identities under one daemon tick. The owner is now read once per tick and the exact returned observation (or same-tick failure) is reused by both projections. The cache refreshes when the tick ID changes. This remains read-only and grants no model, mutation, or execution authority.

The causal-resource provider schema now includes the two chat-process generation fields already emitted by its inspect callback; their absence from the explicit allowlist caused every projection to fail with `owner_projection_shape_changed`. Lightweight runtime surfaces used by daemon closure tests may omit optional transition-recovery fields; guarded reads now preserve normal behavior while retaining the existing block when a configured transition error exists.

## Verification

`python -m scripts.run_tests -q sentientos/tests/test_resource_observation_world_state_integration.py tests/test_sentientosd_causal_introspection_composition.py tests/test_sentientosd_runtime_closure.py tests/test_host_resource_runtime.py tests/test_production_chat_resource_observation_recovery.py tests/test_causal_introspection.py`: 81 passed, 0 skipped. This includes the adversarial observation owner that returns a changed identity on a second read: both same-tick projections retain the first source identity, and the following tick observes the changed identity.

`py_compile` and `git diff --check` passed. `scripts/check_mypy_baseline.py` returned `mypy_baseline_improved`, with 0 new errors and 40 retired error records. A noncanonical direct mypy invocation using the repository's broad configuration reported the repository's existing 837-error state; it is not treated as a pass or as baseline evidence. Initial targeted runs exposed the callback schema mismatch and absent optional test-double fields; the fixed source passed the final 40-node run.

The local pre-commit finalizer returned `repair_required_task_caused`: the focused 81-node run and repository mypy baseline passed, but `verify_audits.py --strict` and `audit_immutability_verifier.py` both failed closed with `Access denied: run as Administrator`. The finalizer did not return `ready_to_commit`; the hosted Required Quality Gate must run the unchanged privileged checks before integration. Post-merge checks remain pending. No production inference, changed-output Federation Health fixture, or authority expansion is claimed.

## Custody

Evidence JSON: `work/construction/evidence/0372-restore-construction-index-and-bind-resource-observations.json`

Evidence SHA-256: `7a7fa0de8fb329673473f3abf40c2455c61bae236107b7c6d3a588288f34bf62`

Source baseline: `a205fdeb280e5488ff6216ab54d7d1800dc0bee8` (tree `a378b176cff01d46697c351944051d5c01af71d0`).

Predecessor: `segment-sha256:a651dfe66e2486f1af03c8077fa0edb54c6401f4a37b4c89bc4aee9096765bd1`
