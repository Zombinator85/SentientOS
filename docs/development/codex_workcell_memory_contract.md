# Codex Workcell Memory Contract

The Codex Workcell Memory Contract defines deterministic, metadata-only schemas
for future `/ledger` receipt-chain records and future `/glow` evidence-archive
records. It is a review grammar for landed Codex workcell evidence; it is not a
storage writer, ledger writer, glow archiver, watcher, scheduler, daemon action,
readiness authority, PR metadata authority, federation consensus mechanism, or
model-training surface.

## Purpose

The workcell ladder is intentionally layered:

1. The workcell architecture names the shape of bounded Codex evidence.
2. The health snapshot observes supplied metadata.
3. The pulse contract names pressure from health metadata.
4. The daemon recommendation contract maps pressure into bounded, non-actionable
   recommendations.
5. This memory contract names how future landed evidence could be represented as
   receipt-chain metadata and archive metadata without performing either action.

## `/ledger` receipt-chain schema, not ledger writing

The `/ledger` section defines canonical field names and record-type catalogs for
future tamper-evident landing history. Record types include landing receipts,
matrix receipts, finalizer receipts, PR metadata guard receipts, evidence index
receipts, appendix provenance receipts, health snapshots, pulse contracts,
daemon recommendation contracts, and this memory contract.

This contract does not write actual ledger entries. It does not validate parent
chains, choose storage paths, verify readiness, authorize commit, authorize PR
metadata, or establish federation consensus. Future active ledger behavior needs
an explicit ledger writer implementation, storage policy, digest verification
policy, parent-chain validation policy, operator consent, and tests proving no
readiness bypass.

## `/glow` evidence-archive schema, not glow archiving

The `/glow` section defines canonical field names and archive item catalogs for
future review-surface memory. Archive item types include workcell architecture,
health snapshot, pulse contract, daemon recommendation contract, evidence index,
evidence appendix markdown, evidence appendix sidecar, doctrine map, matrix
report, finalizer report, and PR metadata guard snapshots.

This contract does not archive files or write glow memory. It does not decide
retention, disclose evidence externally, mutate memory, watch files, poll state,
trigger daemon action, or train models. Future active glow behavior needs an
explicit archiver implementation, retention policy, storage path policy, digest
verification policy, operator consent, and docs marking the behavior active.

## Distinctions from adjacent evidence surfaces

- Health snapshot: observes supplied landing metadata; the memory contract only
  defines future receipt/archive representation for such artifacts.
- Pulse contract: classifies pressure; the memory contract does not consume
  history to produce pressure and does not activate a watcher.
- Daemon recommendation contract: maps pulse signals to non-actionable repair
  recommendations; the memory contract does not recommend repair or trigger a
  daemon.
- Matrix: test/proof evidence; the memory contract defines possible future
  receipt/archive metadata for a matrix report, not matrix truth.
- Finalizer: landing authority for its phase; the memory contract cannot replace
  or bypass finalizer decisions.
- PR metadata guard: authority before PR metadata; the memory contract cannot
  replace or bypass the guard.
- Evidence index and appendix: reviewer evidence surfaces; the memory contract
  only names future ledger/glow roles for them.
- Doctrine map: constraints context; the memory contract preserves `/vow`
  boundaries and forbidden inference rather than training or modifying models.

## Source artifact alignment

The contract maps matrix reports, finalizer reports, PR metadata guard reports,
evidence index artifacts, evidence appendix markdown, evidence appendix sidecars,
doctrine maps, workcell architecture, health snapshots, pulse contracts, daemon
recommendation contracts, and memory contracts to future `/ledger` roles and
future `/glow` roles. Every aligned source expects a digest, but alignment itself
does not create, verify, store, archive, or approve the artifact.

## SentientOS mount alignment

- `/ledger`: future tamper-evident landing history and receipt chain; inactive
  here.
- `/glow`: future archived evidence memory and review-surface archive; inactive
  here.
- `/pulse`: future consumer of ledger/glow history for pressure observation;
  inactive here.
- `/daemon`: future consumer of pulse/recommendation context; inactive here.
- `/vow`: canonical constraints bounding memory interpretation and forbidden
  inference.

## Future activation requirements

All activation requirements are future-only, unmet, and inactive in this task:
explicit ledger writer implementation, explicit glow archiver implementation,
explicit storage path policy, explicit retention policy, explicit digest
verification policy, explicit parent-chain validation policy, explicit operator
consent, explicit finalizer/guard non-bypass invariant, explicit pulse watcher
contract, explicit daemon action contract, explicit federation drift consensus
rule, explicit vow digest constraint check, tests proving no readiness authority,
and docs marking active behavior.

## Non-authority posture

The memory contract is read-only and metadata-only. It does not write ledger,
archive glow, modify memory, watch files, poll state, rerun commands, decide
readiness, bypass the finalizer, bypass the PR metadata guard, authorize commit,
authorize PR creation, trigger a daemon, create tasks, schedule tasks, send
alerts, train or modify models, or establish federation consensus.

## Memory candidate bundle boundary

The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md) can render deterministic candidate `/ledger` entries and candidate `/glow` items from supplied artifacts using these schema families. It is review-only metadata and does not write ledger entries, archive glow evidence, mutate memory, decide readiness, or authorize commit/PR metadata.

## Memory candidate verifier boundary

The [Codex Workcell Memory Candidate Verifier](codex_workcell_memory_candidate_verifier.md) may use this contract to check whether candidate `/ledger` record types and candidate `/glow` archive item types are known. That check is structural metadata only and does not activate ledger writing, glow archiving, readiness authority, daemon action, task creation, scheduling, alerts, or federation consensus.

## Memory activation preflight boundary

See [Codex Workcell Memory Activation Preflight](codex_workcell_memory_activation_preflight.md) for the metadata-only future activation prerequisite report. That preflight does not write `/ledger`, archive `/glow`, mutate memory, decide readiness, authorize PR metadata, trigger daemon action, or create active memory authority.

## Vow boundary note

The [Codex Workcell Vow Digest Boundary Contract](codex_workcell_vow_boundary_contract.md) blocks schema-as-write inference. `/ledger` and `/glow` schemas remain future inactive shapes until separately adopted by explicit writer/archive contracts.

## Vow alignment attestation note

The [Codex Workcell Vow Alignment Attestation Bundle](codex_workcell_vow_alignment_attestation.md) may bind memory contract reports to a supplied vow digest. Schema alignment remains inactive metadata and does not implement ledger writers or glow archivers.
## Storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) extends the memory schemas with future storage path, retention, digest, parent-chain, and vow-bound adoption policy while preserving the rule that schemas are not writes.

## Storage policy verifier boundary

See [Codex Workcell Storage Policy Verifier](codex_workcell_storage_policy_verifier.md) for the metadata-only structural verifier for storage policy contracts. Its verification status is not readiness authority and it does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, schedule tasks, or bypass finalizer/PR metadata guard requirements.
## Storage transaction dry-run planner boundary

The [Codex Workcell Storage Transaction Dry-Run Plan](codex_workcell_storage_transaction_plan.md) is the next metadata-only layer for supplied storage policy, candidate, verifier, and vow reports. It emits future `/ledger` and `/glow` would-write plans only; it does not write, archive, activate memory, decide readiness, bypass finalizer/PR metadata guard, trigger daemons, schedule tasks, or create PRs.

## Storage transaction plan verifier boundary

The [Codex Workcell Storage Transaction Plan Verifier](codex_workcell_storage_transaction_plan_verifier.md) is a deterministic metadata-only structural verifier for dry-run storage transaction plans. It checks planned `/ledger` and `/glow` transaction shape, paths, digests, parent-chain gaps, vow alignment context, transaction gaps, reviewer hygiene metadata, future activation requirements, and non-authority posture; it does not write, archive, activate memory, decide readiness, bypass finalizer/PR metadata guard, trigger daemons, schedule tasks, create PRs, or establish federation consensus.
## Storage execution readiness dossier boundary

The [Codex Workcell Storage Execution Readiness Dossier](codex_workcell_storage_execution_dossier.md) may inventory this report as metadata-only evidence for future active-storage design. It does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, decide readiness, authorize PR metadata, or grant runtime storage authority.

## Storage execution dossier verifier boundary

See [Codex Workcell Storage Execution Dossier Verifier](codex_workcell_storage_execution_dossier_verifier.md) for the metadata-only structural verifier that checks dossier evidence inventory, inactive future activation requirements, active execution gaps, reviewer URL hygiene context, and non-authority posture without granting readiness, storage, ledger, glow, daemon, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority.

## Storage runtime authority boundary contract note

The [Codex Workcell Storage Runtime Authority Boundary Contract](codex_workcell_storage_runtime_authority_contract.md) records future-only runtime binding requirements for active `/ledger` and `/glow` storage. It is metadata-only and does not grant readiness, finalizer authority, PR metadata authority, runtime write authority, ledger writes, glow archives, daemon action, scheduling, memory mutation, or federation consensus.

## Storage runtime authority verifier boundary

See [Codex Workcell Storage Runtime Authority Boundary Verifier](codex_workcell_storage_runtime_authority_verifier.md) for the metadata-only structural verifier that checks the future-only runtime authority contract without granting readiness, binding runtime authority, writing `/ledger`, archiving `/glow`, mutating memory, scheduling work, triggering daemon action, or establishing federation consensus.
