# Sandboxed Live Memory Commit Adapter Packet

`sentientos/sandboxed_live_memory_commit_adapter_packet.py` implements the `sandboxed_live_memory_commit_adapter_packet` capability as a deterministic metadata-only packet surface for review. It consumes Sandboxed Live Memory Commit Adapter Gate evidence via the `sandboxed_live_memory_commit_adapter_gate` key plus explicit `sandboxed_live_memory_commit_adapter_packet_candidates` and emits reviewable JSON metadata for a later sandboxed live memory commit adapter envelope.

The packet is inert. It does not admit real memory roots, write live memory, approve live execution, execute or apply commits, create or admit a live adapter, invoke or enable executors, acquire locks, create lockfiles, retrieve live context, materialize prompts, execute actions, disclose externally, grant authority, or grant permission to execute.

## Evidence contract

The packet validates matching upstream digest and decision evidence from the Sandboxed Live Memory Commit Adapter Gate, mirrors carried evidence from the Sandboxed Live Memory Commit Adapter, Real Memory Root Admission Packet, Real Memory Root Admission Gate, Final Live Memory Commit Review Gate, and the upstream execution/admission/readiness chain, and requires packet candidate scope alignment with the upstream gate scope.

Ready records use `sandboxed_live_memory_commit_adapter_packet_ready_for_later_sandboxed_live_memory_commit_adapter_envelope`. Top-level statuses are:

- `sandboxed_live_memory_commit_adapter_packet_ready`;
- `sandboxed_live_memory_commit_adapter_packet_ready_with_warnings`;
- `sandboxed_live_memory_commit_adapter_packet_deferred_for_operator_review`;
- `sandboxed_live_memory_commit_adapter_packet_noop`;
- `sandboxed_live_memory_commit_adapter_packet_blocked` for invalid, unsafe, or mismatched evidence.

## Default-deny boundary

Outputs keep the authority/runtime/write surface false, including `sandboxed_live_memory_commit_adapter_packet_created`, `sandboxed_live_memory_commit_adapter_packet_authority_created`, `sandboxed_live_memory_commit_adapter_packet_enabled`, `sandboxed_live_memory_commit_adapter_gate_enabled`, `sandboxed_live_memory_commit_adapter_enabled`, `sandboxed_live_memory_commit_adapter_admitted`, `live_adapter_created`, `live_adapter_admitted`, `real_memory_root_admission_enabled`, `real_memory_root_admitted`, `real_memory_root_write_enabled`, `live_memory_write_enabled`, `live_commit_execution_enabled`, `live_commit_applied`, `real_executor_enabled`, `real_executor_invoked`, `runtime_enabled`, `real_lock_acquisition_enabled`, `lockfile_creation_enabled`, `external_disclosure_enabled`, `action_execution_enabled`, `prompt_materialization_enabled`, and `live_context_retrieval_enabled`.

The CLI may print a metadata artifact to stdout, but adapter authority is not created. The separate `sandboxed_live_memory_commit_adapter_packet_authority_created: false` flag documents that distinction.

Future-only flags remain true: `future_sandboxed_live_memory_commit_adapter_envelope_required`, `future_real_live_memory_commit_execution_required`, and `future_post_execution_audit_required`.

## CLI

`scripts/build_sandboxed_live_memory_commit_adapter_packet.py` exposes:

- `build-default` — prints the default policy and validation result;
- `evaluate <packet.json>` — emits deterministic JSON and writes nothing;
- `validate [packet.json]` — validates policy or evaluates a candidate packet;
- `summarize <packet.json>` — prints status, digest, counts, and findings;
- `inspect-fixture <name>` — prints fixture JSON from `tests/fixtures/sandboxed_live_memory_commit_adapter_packet/`.

Blocked, invalid, and failed outcomes exit nonzero.
