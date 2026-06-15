# Sandboxed Live Memory Commit Adapter

`sentientos/sandboxed_live_memory_commit_adapter.py` implements the `sandboxed_live_memory_commit_adapter` capability as a deterministic metadata-only adapter surface for review. It consumes Real Memory Root Admission Packet evidence plus explicit `sandboxed_live_memory_commit_adapter_candidates` and emits reviewable JSON metadata for a later sandboxed adapter gate.

The adapter is sandbox-bound and inert. It does not create a live adapter, admit a live adapter, admit a real memory root, write live memory, apply commits, execute commits, invoke executors, acquire locks, create lockfiles, retrieve live context, materialize prompts, execute actions, disclose externally, grant authority, or grant permission to execute.

## Upstream evidence

Each candidate must carry matching evidence from the immediate upstream packet:

- primary upstream key: `real_memory_root_admission_packet`;
- candidate list key: `sandboxed_live_memory_commit_adapter_candidates`;
- `claimed_real_memory_root_admission_packet_digest` or `claimed_upstream_digest` must match the packet digest;
- `claimed_real_memory_root_admission_packet_decision` or `claimed_upstream_decision` must match the packet decision;
- candidate scope keys must match the packet record scope keys unless the candidate is an explicit mixed-scope diagnostic candidate.

The adapter preserves carried upstream evidence for the Real Memory Root Admission Gate, Final Live Memory Commit Review Gate, adapter readiness envelope/gate, adapter admission packet/gate, live-memory commit execution packet/gate, commit window packet, commit plan gate, and commit plan packet.

## Decisions and statuses

Ready records use `sandboxed_live_memory_commit_adapter_ready_for_later_sandboxed_live_memory_commit_adapter_gate`. Top-level statuses are:

- `sandboxed_live_memory_commit_adapter_ready`;
- `sandboxed_live_memory_commit_adapter_ready_with_warnings`;
- `sandboxed_live_memory_commit_adapter_deferred_for_operator_review`;
- `sandboxed_live_memory_commit_adapter_noop`;
- `sandboxed_live_memory_commit_adapter_blocked` for invalid, unsafe, or mismatched evidence.

## Default-deny flags

Outputs keep the authority/runtime/write surface false, including `sandboxed_live_memory_commit_adapter_authority_created`, `sandboxed_live_memory_commit_adapter_enabled`, `sandboxed_live_memory_commit_adapter_admitted`, `live_adapter_created`, `live_adapter_admitted`, `real_memory_root_admission_enabled`, `real_memory_root_admitted`, `real_memory_root_write_enabled`, `live_memory_write_enabled`, `live_commit_execution_enabled`, `live_commit_applied`, `real_executor_enabled`, `real_executor_invoked`, `runtime_enabled`, `real_lock_acquisition_enabled`, `lockfile_creation_enabled`, `external_disclosure_enabled`, `action_execution_enabled`, `prompt_materialization_enabled`, and `live_context_retrieval_enabled`.

The metadata artifact itself may be emitted by the CLI to stdout, but adapter authority is not created. The separate `sandboxed_live_memory_commit_adapter_authority_created: false` flag documents that distinction.

## Future-only gates

The output sets these future-only requirements to true:

- `future_sandboxed_live_memory_commit_adapter_gate_required`;
- `future_real_live_memory_commit_execution_required`;
- `future_post_execution_audit_required`.

These are requirements for later metadata or live-governed rungs, not current permission.

## CLI

`scripts/build_sandboxed_live_memory_commit_adapter.py` exposes:

- `build-default` — prints the default deny-by-default policy and fixture root.
- `evaluate` — evaluates input and writes nothing.
- `validate` — validates default policy or evaluates an input document.
- `summarize` — prints status, digest, packet digest, counts, and findings.
- `inspect-fixture` — prints fixture JSON from `tests/fixtures/sandboxed_live_memory_commit_adapter/`.

Blocked, invalid, or failed outcomes exit nonzero.

## Fixtures and proof points

Fixtures cover ready, noop, mixed-warning, operator-review, digest mismatch, decision mismatch, live-write claims, real-memory-root access/admission claims, live-adapter creation/admission claims, runtime hook claims, executor authority claims, lock acquisition claims, prompt materialization, live context retrieval, action execution, external disclosure, and unsafe adapter metadata.

The focused tests prove deterministic metadata output, default-deny flags, noop and warning behavior, CLI non-mutation, fixture inspection, and fail-closed handling for blocked claims.
