# SentientOS Real Memory Root Admission Gate

The real memory root admission gate is a deterministic, metadata-only checkpoint after the [sandboxed live memory commit adapter](sandboxed_live_memory_commit_adapter.md). It consumes supplied sandbox commit packet evidence and explicit real-root admission candidates to decide whether a future real live-memory commit adapter may be considered later.

This gate is not the real live-memory commit adapter. It does not write real memory, delete memory, purge memory, mutate live indexes, persist capsules, complete tombs, assemble prompts, retrieve live context, execute actions, disclose externally, create policy, infer truth, infer consent, or grant authority.

## Why the gate exists

Sandboxed commit evidence can show that a proposed memory-chain change has deterministic artifact, receipt-manifest, and rollback-manifest metadata. That evidence still cannot touch the real memory root. The admission gate gives reviewers a separate, default-deny place to check whether explicit future real-root admission metadata is internally consistent before any future adapter is even considered.

## Relationship to sandboxed live memory commit adapter

The upstream sandbox adapter may emit sandbox-only artifacts under a caller-provided sandbox root. The admission gate consumes the resulting sandbox commit packet as evidence only. It requires:

- a sandbox commit packet with records and packet digest;
- a ready sandbox decision such as `sandbox_commit_artifacts_ready`, warning, operator-review, rejection, or noop;
- candidate `claimed_sandbox_commit_digest` matching the sandbox packet digest;
- candidate `claimed_sandbox_commit_decision` matching the sandbox record decision;
- matching operator scope unless mixed diagnostic warning policy explicitly allows diagnostic mismatch.

Sandbox commits are not real commits. Sandbox receipts are not live receipts. Sandbox rollback manifests are not applied rollback. The gate blocks any candidate that claims otherwise.

## Required non-noop evidence

For every non-noop candidate the gate requires:

- `claimed_sandbox_receipt_manifest_digest`;
- `claimed_sandbox_rollback_manifest_digest`;
- `sandbox_artifact_plan` metadata;
- explicit inert `real_root_path_metadata`.

Noop candidates remain deterministic and non-mutating without receipt, rollback, or artifact-plan digests.

## Candidate types

The allowed candidate types are:

- `ai_capsule_real_root_admission_candidate`
- `human_summary_real_root_admission_candidate`
- `dual_capsule_real_root_admission_candidate`
- `protect_receipt_real_root_admission_candidate`
- `merge_receipt_real_root_admission_candidate`
- `tomb_archive_real_root_admission_candidate`
- `tomb_deferred_real_root_admission_candidate`
- `operator_review_real_root_admission_candidate`
- `noop_real_root_admission_candidate`
- `mixed_real_root_admission_candidate`

## Decisions and statuses

Candidate decisions are:

- `real_root_admission_candidate_ready_for_future_adapter`
- `real_root_admission_candidate_ready_with_warnings`
- `real_root_admission_deferred_for_operator_review`
- `real_root_admission_rejected`
- `real_root_admission_blocked`
- `real_root_admission_noop`

Result statuses are `real_root_admission_ready`, `real_root_admission_ready_with_warnings`, `real_root_admission_deferred_for_operator_review`, `real_root_admission_rejected`, `real_root_admission_blocked`, `real_root_admission_noop`, `real_root_admission_invalid`, and `real_root_admission_failed`.

## Real-root path metadata rules

Admission is not memory-root access. Path evidence must be inert metadata, not a filesystem operation. By default the gate blocks missing, absolute, traversal, device, symlink-risk, ambiguous, operator-home, or real/live-memory-root-looking path metadata. Unsafe path strings may be represented only as inert metadata for review when policy explicitly enables `allow_inert_review_path_metadata` and the candidate marks the metadata as explicitly allowed for review.

The library does not validate by touching real memory roots. It does not create, delete, purge, rename, chmod, open for write, or mutate any real memory path.

## Blockers

Hard blockers include missing or invalid sandbox packets, missing or invalid candidates, sandbox not-ready evidence, sandbox digest mismatch, sandbox decision mismatch, missing non-noop receipt manifest digest, missing non-noop rollback manifest digest, missing non-noop sandbox artifact plan, real-memory-root access claims, live write/delete/purge/index mutation claims, path traversal, unsafe root metadata, sandbox-to-real conversion claims, prompt materialization, live context retrieval, action execution, external disclosure, authority/consent/policy/truth smuggling, raw/private/media/secret/provider-prompt payload leakage, and scope mismatch.

Operator review cannot override hard blockers.

## Safe next actions and forbidden next steps

Safe next actions are limited to inspecting the admission packet, operator review, preparing a future real live-memory commit adapter later, preparing final operator review later, rerunning with corrected metadata, and sustaining default deny.

Forbidden next steps include real live-memory write/delete/purge, live index mutation, prompt assembly, live context retrieval, action ingress, treating sandbox commits as real commits, treating sandbox receipts as live receipts, treating sandbox rollback as applied rollback, sandbox bypass, real-root admission bypass, upstream gate bypass, and external disclosure.

## Lifecycle

The intended lifecycle remains:

1. Selective memory distillation contract.
2. Selective memory distillation receipt gate.
3. Selective memory tomb receipt verifier.
4. Governed memory writer adapter.
5. Live memory boundary admission gate.
6. Memory commit plan packet.
7. Memory commit operator approval packet.
8. Memory commit execution gate.
9. Live memory commit dry-run adapter.
10. Live commit safety interlock.
11. Sandboxed live memory commit adapter.
12. Real memory root admission gate.
13. Future real live-memory commit adapter only after separate implementation and final operator review.

Step 12 does not perform step 13. Future real live commit adapter implementation remains required, and final operator review remains required.

## CLI and validation

`scripts/build_real_memory_root_admission_gate.py` supports `build-default`, `evaluate`, `validate`, `summarize`, and `inspect-fixture`. `evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or failed outcomes exit nonzero.

Fixtures live under `tests/fixtures/real_memory_root_admission_gate/`. The capability is registered as `real_memory_root_admission_gate`, appears in the reviewer proof bundle, and is covered by the work-item review packet matrix lane `real_memory_root_admission_gate_tests`.
