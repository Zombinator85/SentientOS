# Memory Commit Execution Gate

The memory commit execution gate is a deterministic, metadata-only review layer after the [memory commit plan packet](memory_commit_plan_packet.md) and [memory commit operator approval packet](memory_commit_operator_approval_packet.md). It evaluates supplied plan-packet metadata, operator-approval metadata, and explicit execution-candidate metadata to decide whether a future live memory commit adapter may later be considered.

The gate is not a live adapter. It is default-deny, non-mutating, non-executing, and non-authoritative. It never writes live memory, deletes memory, purges memory, mutates indexes, persists capsules, applies protection, applies merges, completes tombs, runs live commits, executes commit plans, executes operator approvals, assembles prompts, retrieves live context, executes action ingress, discloses externally, infers truth, infers consent, creates policy, grants authority, or bypasses the distillation/receipt/tomb/writer/boundary/plan/approval chain.

## Inputs

The library and CLI accept JSON containing:

1. `commit_plan_packet`: a metadata packet with at least one plan record, packet digest, and plan decision.
2. `operator_approval_packet`: a metadata packet with at least one approval record, packet digest, approval decision, and operator scope.
3. `execution_candidate` or `execution_candidates`: explicit metadata-only execution-gate candidates with claimed plan/approval digests, claimed plan/approval decisions, operator scope, gate preconditions, rollback expectation, receipt expectation, and execution claims.
4. Optional `policy`: deterministic gate policy toggles. The default policy is deny-by-default and blocks missing preconditions, missing scope, mismatches, and any hard execution or authority overclaim.

## API surface

`sentientos.memory_commit_execution_gate` exposes:

- `MemoryCommitExecutionGatePolicy`
- `MemoryCommitExecutionGateInput`
- `MemoryCommitExecutionGateCandidate`
- `MemoryCommitExecutionGateFinding`
- `MemoryCommitExecutionGatePrecondition`
- `MemoryCommitExecutionGateRecord`
- `MemoryCommitExecutionGatePacket`
- `MemoryCommitExecutionGateReport`
- `MemoryCommitExecutionGateResult`
- `build_default_policy()`
- `validate_policy()`
- `evaluate_memory_commit_execution_gate()`
- `evaluate_packet()`

Successful packets carry deterministic `sha256:` digests for records, packet, report, and result.

## Decisions

Execution records use one of these decisions:

- `commit_execution_eligible_for_future_adapter`
- `commit_execution_eligible_for_future_adapter_with_warnings`
- `commit_execution_deferred_for_operator_review`
- `commit_execution_rejected`
- `commit_execution_blocked`
- `commit_execution_noop`

Result statuses distinguish ready, warning, deferred, rejected, noop, blocked, invalid, and failed outcomes. Blocked/invalid/failed outcomes do not produce a packet.

## Default-deny and future adapter boundaries

Every successful packet affirms that the gate is not memory write, not memory deletion, not index mutation, not capsule persistence, not prompt assembly, not execution, not live commit, not truth, not policy, not authority, and not consent. It also records that live memory write, live deletion, live index mutation, capsule persistence, prompt materialization, external disclosure, and remote service use are disabled.

The packet requires a future commit adapter, a future live dry-run, rollback expectation, receipt expectation, and operator approval. Eligibility means only that a later adapter could be reviewed; it does not authorize implementation, execution, or mutation.

## Blocking behavior

The gate blocks when any required packet or candidate is missing or invalid; when commit plan or operator approval evidence is not ready; when claimed plan/approval digests or decisions mismatch supplied packets; when gate preconditions are missing or false; when operator scope is missing; when scope mismatches; when rollback or receipt expectations are missing for non-noop candidates; when execution overclaims appear; when live write/delete, index mutation, capsule persistence, prompt materialization, action execution, external disclosure, authority smuggling, or raw payload leaks are claimed; and when mixed-scope diagnostic packets are supplied without `allow_mixed_scope_diagnostic_packet`.

Operator review cannot override hard blockers. A review request may defer an otherwise safe candidate, but it cannot convert an execution claim, authority claim, raw payload leak, digest mismatch, decision mismatch, missing precondition, or scope mismatch into eligibility.

## CLI

`scripts/build_memory_commit_execution_gate.py` supports:

- `build-default`
- `evaluate --input JSON`
- `validate [--input JSON]`
- `summarize --input JSON`
- `inspect-fixture --fixtures-dir PATH --fixture-name NAME`
- `--output JSON`
- `--summary`

The CLI emits deterministic JSON. It exits nonzero for blocked, invalid, or failed outcomes. The CLI and library do not write live memory, delete files, mutate indexes, execute commits, launch external processes from library code, or invoke remote services.

## Fixtures and proof

Metadata-only fixtures live under `tests/fixtures/memory_commit_execution_gate/`. They cover valid capsule, summary, dual, protect, merge, tomb, operator-review, noop, warning, and mixed diagnostic candidates plus blocked missing-packet, mismatch, precondition, scope, expectation, execution-overclaim, live-write/delete, index-mutation, capsule-persistence, prompt-materialization, action-execution, external-disclosure, authority-smuggling, raw-payload-leak, and scope-mismatch cases.

Proof commands:

```bash
python -m scripts.run_tests -q tests/test_memory_commit_execution_gate.py tests/test_build_memory_commit_execution_gate_script.py
python -m mypy sentientos/memory_commit_execution_gate.py scripts/build_memory_commit_execution_gate.py
```

The work-item review packet matrix includes `memory_commit_execution_gate_tests` and targeted mypy coverage for the module and CLI.
