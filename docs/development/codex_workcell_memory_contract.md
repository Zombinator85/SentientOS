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
