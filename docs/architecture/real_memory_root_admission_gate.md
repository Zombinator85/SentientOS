# Real Memory Root Admission Gate

The Real Memory Root Admission Gate is a deterministic, metadata-only memory-chain rung after the merged [Final Live Memory Commit Review Gate](final_live_memory_commit_review_gate.md). It consumes supplied `final_live_memory_commit_review_gate` evidence and explicit `real_memory_root_admission_gate_candidates` to produce reviewable readiness metadata for a later Real Memory Root Admission Packet rung.

The gate is default-deny. It does not admit real memory roots, create a real memory root admission packet, approve live execution, execute or apply commits, write live memory, create or admit live adapters, invoke or activate executors, release execution, issue permits, authorize execution, enable runtime, acquire locks, create lockfiles, disclose externally, retrieve live context, materialize prompts, grant authority, or grant permission to execute.

## Inputs

- `final_live_memory_commit_review_gate`: evaluated Final Live Memory Commit Review Gate metadata, normally the `gate` object emitted by `scripts/build_final_live_memory_commit_review_gate.py evaluate`.
- `real_memory_root_admission_gate_candidates`: one or more explicit candidate records.

The preexisting compatibility fixture names using `real_root_admission` remain accepted for repository callers and tests, but the canonical post-#1855 input key is `real_memory_root_admission_gate_candidates`.

## Candidate types

Canonical candidate types are:

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

Compatibility candidate type aliases using the older `real_root_admission` token are accepted only as inert metadata aliases.

## Decisions and statuses

Candidate decisions include:

- `real_memory_root_admission_gate_ready_for_later_real_memory_root_admission_packet`
- `real_memory_root_admission_gate_ready_with_warnings`
- `real_memory_root_admission_gate_deferred_for_operator_review`
- `real_memory_root_admission_gate_rejected`
- `real_memory_root_admission_gate_blocked`
- `real_memory_root_admission_gate_noop`

Result statuses are `real_memory_root_admission_gate_ready`, `real_memory_root_admission_gate_ready_with_warnings`, `real_memory_root_admission_gate_deferred_for_operator_review`, `real_memory_root_admission_gate_rejected`, `real_memory_root_admission_gate_blocked`, `real_memory_root_admission_gate_noop`, `real_memory_root_admission_gate_invalid`, and `real_memory_root_admission_gate_failed`.

## Required evidence

The gate requires matching upstream digest and decision evidence from the Final Live Memory Commit Review Gate:

- `claimed_final_live_memory_commit_review_gate_digest`
- `claimed_final_live_memory_commit_review_gate_decision`

Candidate scope must align with the Final Live Memory Commit Review Gate record scope. Mixed candidates may report warning-only diagnostic scope mismatch when policy allows mixed-scope diagnostics.

The gate preserves carried upstream evidence from the Final Live Memory Commit Review Gate record, including adapter readiness, adapter admission, live memory commit execution, commit window, and commit plan metadata when present.

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

The emitted gate and records keep default-deny flags false, including:

- `real_memory_root_admission_gate_passed`
- `real_memory_root_admission_enabled`
- `real_memory_root_admission_packet_created`
- `real_memory_root_admitted`
- `live_memory_write_enabled`
- `live_commit_execution_enabled`
- `live_commit_applied`
- `live_adapter_created`
- `live_adapter_admitted`
- executor, runtime, lock, and lockfile authority flags

The emitted future-only flag `future_real_memory_root_admission_packet_required` is true. The only safe forward step is a later Real Memory Root Admission Packet metadata rung.

## Blockers

Hard blockers include missing Final Live Memory Commit Review Gate evidence, missing candidates, invalid candidate types, final-review digest mismatch, final-review decision mismatch, non-ready final-review evidence, scope mismatch outside diagnostic mixed mode, and any claim that would admit roots, create an admission packet, approve or execute commits, write live memory, create/admit adapters, invoke/activate/release/authorize executors, issue permits, enable runtime, acquire locks, create lockfiles, retrieve live context, materialize prompts, disclose externally, or grant authority or permission to execute.

Operator review cannot override hard blockers.

## CLI

Use `scripts/build_real_memory_root_admission_gate.py`:

```bash
python scripts/build_real_memory_root_admission_gate.py build-default
python scripts/build_real_memory_root_admission_gate.py evaluate tests/fixtures/real_memory_root_admission_gate/ready_real_memory_root_admission_gate_candidate.json
python scripts/build_real_memory_root_admission_gate.py validate tests/fixtures/real_memory_root_admission_gate/ready_real_memory_root_admission_gate_candidate.json
python scripts/build_real_memory_root_admission_gate.py summarize tests/fixtures/real_memory_root_admission_gate/ready_real_memory_root_admission_gate_candidate.json
python scripts/build_real_memory_root_admission_gate.py inspect-fixture ready_real_memory_root_admission_gate_candidate
```

`evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or failed outcomes exit nonzero.

Fixtures live under `tests/fixtures/real_memory_root_admission_gate/`. Canonical ready/noop/mixed fixtures are `ready_real_memory_root_admission_gate_candidate.json`, `noop_real_memory_root_admission_gate_candidate.json`, and `mixed_real_memory_root_admission_gate_candidate.json`; compatibility fixtures using older names are retained for callers. The capability is registered as `real_memory_root_admission_gate`, appears in the reviewer proof bundle, and is covered by the work-item review packet matrix lane `real_memory_root_admission_gate_tests`.
