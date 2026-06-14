# SentientOS Real Memory Root Admission Gate

The real memory root admission gate is a deterministic, metadata-only checkpoint after the [Final Live Memory Commit Review Gate](final_live_memory_commit_review_gate.md). It consumes supplied final live memory commit review gate evidence and explicit real memory root admission gate candidates to produce readiness metadata for a later Real Memory Root Admission Packet.

This gate is not the real live-memory commit adapter. It does not write real memory, delete memory, purge memory, mutate live indexes, persist capsules, complete tombs, assemble prompts, retrieve live context, execute actions, disclose externally, create policy, infer truth, infer consent, or grant authority.

## Why the gate exists

Sandboxed commit evidence can show that a proposed memory-chain change has deterministic artifact, receipt-manifest, and rollback-manifest metadata. That evidence still cannot touch the real memory root. The admission gate gives reviewers a separate, default-deny place to check whether explicit future real-root admission metadata is internally consistent before any future adapter is even considered.

## Relationship to Final Live Memory Commit Review Gate

The upstream Final Live Memory Commit Review Gate emits metadata-only review evidence. The admission gate consumes that evidence only. It requires:

- a final live memory commit review gate evidence object with records and digest;
- a ready final review decision such as `final_live_memory_commit_review_gate_ready_for_later_real_memory_root_admission_gate`, warning, operator-review, rejection, or noop;
- candidate claimed upstream digest matching the final review gate digest;
- candidate claimed upstream decision matching the final review gate decision;
- matching operator scope between final review evidence and the admission candidate unless mixed diagnostic warning policy explicitly allows diagnostic mismatch.

Final review evidence is not execution approval, root admission, a live commit, a live receipt, an applied rollback, authority, or permission to execute. The gate blocks any candidate that claims otherwise.

## Required non-noop evidence

For every non-noop candidate the gate requires:

- `claimed_sandbox_receipt_manifest_digest`;
- `claimed_sandbox_rollback_manifest_digest`;
- `sandbox_artifact_plan` metadata;
- explicit inert `real_root_path_metadata`.

Noop candidates remain deterministic and non-mutating without receipt, rollback, or artifact-plan digests.

## Candidate types

The allowed candidate types are:

- `ai_capsule_real_memory_root_admission_gate_candidate`
- `human_summary_real_memory_root_admission_gate_candidate`
- `dual_capsule_real_memory_root_admission_gate_candidate`
- `protect_receipt_real_memory_root_admission_gate_candidate`
- `merge_receipt_real_memory_root_admission_gate_candidate`
- `tomb_archive_real_memory_root_admission_gate_candidate`
- `tomb_deferred_real_memory_root_admission_gate_candidate`
- `operator_review_real_memory_root_admission_gate_candidate`
- `noop_real_memory_root_admission_gate_candidate`
- `mixed_real_memory_root_admission_gate_candidate`

## Decisions and statuses

Candidate decisions are:

- `real_memory_root_admission_gate_ready_for_later_real_memory_root_admission_packet`
- `real_memory_root_admission_gate_ready_with_warnings`
- `real_memory_root_admission_gate_deferred_for_operator_review`
- `real_memory_root_admission_gate_rejected`
- `real_memory_root_admission_gate_blocked`
- `real_memory_root_admission_gate_noop`

Result statuses are `real_memory_root_admission_gate_ready`, `real_memory_root_admission_gate_ready_with_warnings`, `real_memory_root_admission_gate_deferred_for_operator_review`, `real_memory_root_admission_gate_rejected`, `real_memory_root_admission_gate_blocked`, `real_memory_root_admission_gate_noop`, `real_memory_root_admission_gate_invalid`, and `real_memory_root_admission_gate_failed`.

## Real-root path metadata rules

Admission is not memory-root access. Path evidence must be inert metadata, not a filesystem operation. By default the gate blocks missing, absolute, traversal, device, symlink-risk, ambiguous, operator-home, or real/live-memory-root-looking path metadata. Unsafe path strings may be represented only as inert metadata for review when policy explicitly enables `allow_inert_review_path_metadata` and the candidate marks the metadata as explicitly allowed for review.

The library does not validate by touching real memory roots. It does not create, delete, purge, rename, chmod, open for write, or mutate any real memory path.

## Blockers

Hard blockers include missing or invalid sandbox packets, missing or invalid candidates, sandbox not-ready evidence, sandbox digest mismatch, sandbox decision mismatch, missing non-noop receipt manifest digest, missing non-noop rollback manifest digest, missing non-noop sandbox artifact plan, real-memory-root access claims, live write/delete/purge/index mutation claims, path traversal, unsafe root metadata, sandbox-to-real conversion claims, prompt materialization, live context retrieval, action execution, external disclosure, authority/consent/policy/truth smuggling, raw/private/media/secret/provider-prompt payload leakage, and scope mismatch.

Operator review cannot override hard blockers.

## Safe next actions and forbidden next steps

Safe next actions are limited to inspecting the admission packet, operator review, preparing a later Real Memory Root Admission Packet metadata rung, rerunning with corrected metadata, and sustaining default deny.

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
12. Final Live Memory Commit Review Gate.
13. Real Memory Root Admission Gate.
14. Later Real Memory Root Admission Packet metadata rung.

Step 13 does not perform step 14. It does not admit real roots, create an admission packet, approve live execution, apply commits, acquire locks, create lockfiles, invoke executors, enable runtime, create/admit adapters, or grant permission to execute.

## CLI and validation

`scripts/build_real_memory_root_admission_gate.py` supports `build-default`, `evaluate`, `validate`, `summarize`, and `inspect-fixture`. `evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or failed outcomes exit nonzero.

Fixtures live under `tests/fixtures/real_memory_root_admission_gate/`. The capability is registered as `real_memory_root_admission_gate`, appears in the reviewer proof bundle, and is covered by the work-item review packet matrix lane `real_memory_root_admission_gate_tests`.
