# Real Memory Root Admission Packet

The Real Memory Root Admission Packet is a deterministic, metadata-only memory-chain rung after the merged [Real Memory Root Admission Gate](real_memory_root_admission_gate.md). It consumes supplied `real_memory_root_admission_gate` evidence and explicit `real_memory_root_admission_packet_candidates` to produce reviewable packet metadata for a later Sandboxed Live Memory Commit Adapter metadata rung.

The packet is default-deny. It does not admit real memory roots, create a real memory root admission packet, approve live execution, execute or apply commits, write live memory, create or admit live adapters, invoke or activate executors, release execution, issue permits, authorize execution, enable runtime, acquire locks, create lockfiles, disclose externally, retrieve live context, materialize prompts, grant authority, or grant permission to execute.

## Inputs

- `real_memory_root_admission_gate`: evaluated Real Memory Root Admission Gate metadata, normally the `gate` object emitted by `scripts/build_real_memory_root_admission_gate.py evaluate`.
- `real_memory_root_admission_packet_candidates`: one or more explicit candidate records.

The preexisting compatibility fixture names using `real_root_admission` remain accepted for repository callers and tests, but the canonical post-#1857 input key is `real_memory_root_admission_packet_candidates`.

## Candidate types

Canonical candidate types are:

- `ai_capsule_real_memory_root_admission_packet_candidate`
- `human_summary_real_memory_root_admission_packet_candidate`
- `dual_capsule_real_memory_root_admission_packet_candidate`
- `protect_receipt_real_memory_root_admission_packet_candidate`
- `merge_receipt_real_memory_root_admission_packet_candidate`
- `tomb_archive_real_memory_root_admission_packet_candidate`
- `tomb_deferred_real_memory_root_admission_packet_candidate`
- `operator_review_real_memory_root_admission_packet_candidate`
- `noop_real_memory_root_admission_packet_candidate`
- `mixed_real_memory_root_admission_packet_candidate`

Compatibility candidate type aliases using the older `real_root_admission` token are accepted only as inert metadata aliases.

## Decisions and statuses

Candidate decisions include:

- `real_memory_root_admission_packet_ready_for_later_sandboxed_live_memory_commit_adapter`
- `real_memory_root_admission_packet_ready_with_warnings`
- `real_memory_root_admission_packet_deferred_for_operator_review`
- `real_memory_root_admission_packet_rejected`
- `real_memory_root_admission_packet_blocked`
- `real_memory_root_admission_packet_noop`

Result statuses are `real_memory_root_admission_packet_ready`, `real_memory_root_admission_packet_ready_with_warnings`, `real_memory_root_admission_packet_deferred_for_operator_review`, `real_memory_root_admission_packet_rejected`, `real_memory_root_admission_packet_blocked`, `real_memory_root_admission_packet_noop`, `real_memory_root_admission_packet_invalid`, and `real_memory_root_admission_packet_failed`.

## Required evidence

The packet requires matching upstream digest and decision evidence from the Real Memory Root Admission Gate:

- `claimed_real_memory_root_admission_gate_digest`
- `claimed_real_memory_root_admission_gate_decision`

Candidate scope must align with the Real Memory Root Admission Gate record scope. Mixed candidates may report warning-only diagnostic scope mismatch when policy allows mixed-scope diagnostics.

The packet preserves carried upstream evidence from the Real Memory Root Admission Gate record, including Real Memory Root Admission Gate confirmation, Final Live Memory Commit Review Gate evidence, adapter readiness, adapter admission, live memory commit execution, commit window, and commit plan metadata when present.

## Metadata-only record families

Non-noop candidates carry deterministic metadata-only readiness and evidence records for:

- real memory root admission readiness
- final review gate confirmation
- adapter readiness envelope, adapter readiness gate, adapter admission packet, and adapter admission gate confirmation
- live memory commit execution packet and live memory commit execution gate confirmation
- commit window packet, commit plan gate, and commit plan packet confirmation
- live commit execution denial
- live memory write denial
- real memory root admission deferral
- emergency-stop confirmation
- rollback readiness
- verification readiness
- audit readiness

Each record is inert metadata. It is not a packet, approval, execution permission, runtime state, lock lease, lockfile, live adapter, live receipt, applied rollback, or live-memory write.

## Default-deny flags

The emitted packet and records keep default-deny flags false, including:

- `real_memory_root_admission_gate_passed` (false authority flag; metadata confirmation is reported separately)
- `real_memory_root_admission_enabled`
- `real_memory_root_admission_packet_created`
- `real_memory_root_admitted`
- `live_memory_write_enabled`
- `live_commit_execution_enabled`
- `live_commit_applied`
- `live_adapter_created`
- `live_adapter_admitted`
- executor, runtime, lock, and lockfile authority flags

The emitted future-only flags `future_sandboxed_live_memory_commit_adapter_required`, `future_real_live_memory_commit_execution_required`, and `future_post_execution_audit_required` are true. The only safe forward step is a later Sandboxed Live Memory Commit Adapter metadata rung.

## Blockers

Hard blockers include missing Real Memory Root Admission Gate evidence, missing candidates, invalid candidate types, upstream gate digest mismatch, upstream gate decision mismatch, non-ready upstream gate evidence, scope mismatch outside diagnostic mixed mode, and any claim that would admit roots, create an admission packet, approve or execute commits, write live memory, create/admit adapters, invoke/activate/release/authorize executors, issue permits, enable runtime, acquire locks, create lockfiles, retrieve live context, materialize prompts, disclose externally, or grant authority or permission to execute.

Operator review cannot override hard blockers.

## CLI

Use `scripts/build_real_memory_root_admission_packet.py`:

```bash
python scripts/build_real_memory_root_admission_packet.py build-default
python scripts/build_real_memory_root_admission_packet.py evaluate tests/fixtures/real_memory_root_admission_packet/ready_real_memory_root_admission_packet_candidate.json
python scripts/build_real_memory_root_admission_packet.py validate tests/fixtures/real_memory_root_admission_packet/ready_real_memory_root_admission_packet_candidate.json
python scripts/build_real_memory_root_admission_packet.py summarize tests/fixtures/real_memory_root_admission_packet/ready_real_memory_root_admission_packet_candidate.json
python scripts/build_real_memory_root_admission_packet.py inspect-fixture ready_real_memory_root_admission_packet_candidate
```

`evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or failed outcomes exit nonzero.

Fixtures live under `tests/fixtures/real_memory_root_admission_packet/`. Canonical ready/noop/mixed fixtures are `ready_real_memory_root_admission_packet_candidate.json`, `noop_real_memory_root_admission_packet_candidate.json`, and `mixed_real_memory_root_admission_packet_candidate.json`; compatibility fixtures using older names are retained for callers. The capability is registered as `real_memory_root_admission_packet`, appears in the reviewer proof bundle, and is covered by the work-item review packet matrix lane `real_memory_root_admission_packet_tests`.
