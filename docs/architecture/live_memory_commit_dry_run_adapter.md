# Live Memory Commit Dry-Run Adapter

The live memory commit dry-run adapter is a deterministic, metadata-only layer after the [memory commit execution gate](memory_commit_execution_gate.md) and before any future real live-memory commit adapter. It consumes supplied execution-gate packet evidence and proposed dry-run commit candidates, then emits hypothetical operation previews, simulated receipt previews, rollback previews, blocker findings, deterministic digests, and safe next-action metadata.

The adapter is not a live commit adapter. It is default-deny, non-mutating, non-executing, non-authoritative, and dry-run-only. It never writes live memory, deletes memory, purges memory, mutates raw fragments, mutates vector indexes, mutates distilled memory, persists capsules, persists summaries, applies protection, applies merges, completes tombs, runs a live commit, executes a dry run as a commit, executes commit plans, executes operator approvals, assembles prompts, retrieves live context, executes action ingress, discloses externally, calls remote services, infers truth, infers consent, creates policy, grants authority, or bypasses the distillation/receipt/tomb/writer/boundary/plan/approval/execution-gate chain.

## Inputs

The library and CLI accept JSON containing:

1. `execution_gate_packet`: metadata emitted by `sentientos.memory_commit_execution_gate`, including at least one execution-gate record, packet digest, execution decision, and operator scope.
2. `commit_candidate` or `commit_candidates`: explicit metadata-only dry-run candidates with claimed execution-gate digest, claimed execution-gate decision, operator scope, dry-run claims, operation preview, receipt preview, rollback preview, and metadata.
3. Optional `policy`: deterministic dry-run policy toggles. The default policy is deny-by-default and blocks missing evidence, mismatches, missing previews, hard mutation claims, authority smuggling, raw payload leaks, and scope mismatches.

Fixtures intentionally contain only synthetic metadata. They contain no images, audio, video, screenshots, thumbnails, encoded media payloads, raw transcripts, secrets, provider prompts, real private payloads, real home paths, or live memory paths.

## API surface

`sentientos.live_memory_commit_dry_run_adapter` exposes:

- `LiveMemoryCommitDryRunPolicy`
- `LiveMemoryCommitDryRunInput`
- `LiveMemoryCommitDryRunCandidate`
- `LiveMemoryCommitDryRunFinding`
- `LiveMemoryCommitDryRunOperationPreview`
- `LiveMemoryCommitDryRunReceiptPreview`
- `LiveMemoryCommitDryRunRollbackPreview`
- `LiveMemoryCommitDryRunRecord`
- `LiveMemoryCommitDryRunPacket`
- `LiveMemoryCommitDryRunReport`
- `LiveMemoryCommitDryRunResult`
- `build_default_policy()`
- `validate_policy()`
- `evaluate_live_memory_commit_dry_run_adapter()`
- `evaluate_packet()`

Successful packets carry deterministic `sha256:` digests for operation previews, receipt previews, rollback previews, records, packet, report, and result.

## Dry-run candidate and decision behavior

Supported candidate types are:

- `ai_capsule_commit_dry_run_candidate`
- `human_summary_commit_dry_run_candidate`
- `dual_capsule_commit_dry_run_candidate`
- `protect_receipt_commit_dry_run_candidate`
- `merge_receipt_commit_dry_run_candidate`
- `tomb_archive_commit_dry_run_candidate`
- `tomb_deferred_commit_dry_run_candidate`
- `operator_review_commit_dry_run_candidate`
- `noop_commit_dry_run_candidate`
- `mixed_commit_dry_run_candidate`

Records use one of these dry-run decisions:

- `dry_run_commit_preview_ready`
- `dry_run_commit_preview_ready_with_warnings`
- `dry_run_deferred_for_operator_review`
- `dry_run_rejected`
- `dry_run_blocked`
- `dry_run_noop`

Result statuses distinguish ready, ready-with-warnings, deferred, rejected, noop, blocked, invalid, and failed outcomes. Blocked/invalid/failed outcomes do not produce a packet.

## Operation, receipt, and rollback previews

Non-noop dry-run candidates require all three preview surfaces by default:

- `operation_preview` must remain hypothetical. It blocks if it claims applied state, live-memory writes/deletes/purges, index mutation, capsule persistence, or tomb completion.
- `receipt_preview` must remain hypothetical. It blocks if it claims a receipt was already emitted.
- `rollback_preview` must remain hypothetical. It blocks if it claims rollback was already applied.

These previews model only future adapter considerations. They are not receipts, rollback receipts, persistence evidence, execution evidence, or live-memory state.

## Execution-gate matching behavior

The adapter requires a syntactically valid execution-gate packet. The candidate must reference the supplied execution-gate packet digest and execution-gate decision. The execution-gate decision must be one of:

- `commit_execution_eligible_for_future_adapter`
- `commit_execution_eligible_for_future_adapter_with_warnings`
- `commit_execution_deferred_for_operator_review`
- `commit_execution_rejected`
- `commit_execution_noop`

Digest mismatch, decision mismatch, missing packet, invalid packet, or not-ready execution-gate evidence blocks by default.

## Blocking behavior

The dry-run adapter blocks when any required execution-gate packet or commit candidate is missing or invalid; when execution-gate evidence is not ready; when claimed execution-gate digest or decision mismatches; when non-noop candidates omit operation, receipt, or rollback previews; when operation previews claim applied state; when receipt previews claim receipt emission happened; when rollback previews claim rollback happened; when live write/delete/purge, index mutation, capsule persistence, tomb completion, prompt materialization, action execution, external disclosure, authority, consent, policy, truth, action authority, or hard override attempts are claimed; when raw/private/media/encoded/secret/prompt payloads appear; and when scope mismatches by default.

Mixed-scope diagnostics warn only when `allow_mixed_scope_diagnostic_packet` is true. Operator review can defer otherwise safe metadata, but it cannot override hard blockers.

## Default-deny and future adapter boundaries

Every successful packet affirms that the dry run is not memory write, not memory deletion, not index mutation, not capsule persistence, not prompt assembly, not execution, not live commit, not truth, not policy, not authority, and not consent. It also records that the dry run does not execute actions or disclose externally and that live memory write, live deletion, live index mutation, capsule persistence, prompt materialization, external disclosure, and remote service use are disabled.

Successful packets require a future commit adapter, future safety interlock, receipt preview, rollback preview, and execution gate. Dry-run readiness is only metadata for later review; it is never authority to commit.

## Forbidden next steps

Successful packets include explicit forbidden next steps, including writing/deleting/purging live memory, mutating raw fragments or vector indexes, persisting capsules or summaries, applying protection or merges, completing tombs, running live commits, executing dry runs as commits, executing commit plans or operator approvals, treating dry runs as execution or live commits, calling memory mutation APIs, assembling prompts, retrieving live context, executing action ingress, inferring truth/authority/consent, converting dry runs to policy or action, bypassing any upstream memory gate, bypassing operator review, or enabling external disclosure.

## CLI

`scripts/build_live_memory_commit_dry_run_adapter.py` supports:

- `build-default`
- `evaluate --input JSON`
- `validate [--input JSON]`
- `summarize --input JSON`
- `inspect-fixture --fixtures-dir PATH --fixture-name NAME`
- `--output JSON`
- `--summary`

The CLI emits deterministic JSON. It exits nonzero for blocked, invalid, or failed outcomes. The CLI and library do not write live memory, delete files, mutate indexes, execute commits, launch external processes from library code, or invoke remote services.

## Fixtures and proof

Metadata-only fixtures live under `tests/fixtures/live_memory_commit_dry_run_adapter/`. They cover valid capsule, summary, dual, protect, merge, tomb, operator-review, noop, warning, and mixed diagnostic candidates plus blocked missing-packet, invalid-packet, missing-candidate, invalid-candidate, not-ready execution gate, digest mismatch, decision mismatch, missing preview, preview mismatch, live-write/delete, index-mutation, capsule-persistence, tomb-completion, prompt-materialization, action-execution, external-disclosure, authority-smuggling, raw-payload-leak, and scope-mismatch cases.

Proof commands:

```bash
python -m scripts.run_tests -q tests/test_live_memory_commit_dry_run_adapter.py tests/test_build_live_memory_commit_dry_run_adapter_script.py
python -m mypy sentientos/live_memory_commit_dry_run_adapter.py scripts/build_live_memory_commit_dry_run_adapter.py
```

The work-item review packet matrix includes `live_memory_commit_dry_run_adapter_tests` and targeted mypy coverage for the module and CLI. The capability registry and reviewer proof bundle expose `live_memory_commit_dry_run_adapter` as metadata-only verification capability evidence.
