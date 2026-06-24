# Codex Workcell Memory Candidate Verifier

The Codex Workcell Memory Candidate Verifier is a deterministic, metadata-only
inspection surface for JSON emitted by the Codex Workcell Memory Candidate
Bundle. It reads a supplied candidate bundle JSON, optionally reads a supplied
memory contract JSON, and emits a structural verification report for reviewer
inspection.

It is verifier-only. It does not write `/ledger` entries, archive `/glow`
evidence, mutate memory, watch files, poll state, rerun commands, schedule work,
trigger daemon action, create tasks, send alerts, decide readiness, authorize
commit, authorize PR metadata, create PRs, establish federation consensus, train
models, or modify models.

## Contract, candidate bundle, and verifier

- The [Codex Workcell Memory Contract](codex_workcell_memory_contract.md)
  defines future `/ledger` receipt-chain record types and future `/glow` archive
  item types. It is schema metadata, not a writer.
- The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md)
  renders candidate `/ledger` receipt entries and candidate `/glow` archive
  records from supplied artifacts. It is candidate metadata, not storage.
- This verifier checks whether a supplied candidate bundle is internally
  consistent and, when a memory contract is supplied, whether candidate record
  and archive types are known by that contract.

## Structural checks

The verifier reports deterministic check objects with a stable `check_id`,
`passed` boolean, `severity`, `details`, and `authority_boundary`. Checks cover:

- bundle object shape and metadata-only/candidate-only declarations;
- no-ledger-write and no-glow-archive declarations;
- input summaries, candidate ledger entries, candidate glow items, and source
  artifact map shape;
- uniqueness of candidate ledger entry ids and candidate glow item ids;
- ledger/glow references to provided inputs;
- source artifact map links to existing candidate ledger/glow ids;
- candidate chain/archive summary count agreement;
- per-entry `candidate_only`, `no_write_performed`, and
  `no_archive_performed` flags;
- inactive future activation requirements;
- non-authority posture presence and true values;
- contract-known record and archive item types when a memory contract is
  supplied.

## Verification status is not readiness authority

`verification_status` is only bundle-structure status. It may be
`memory_candidate_bundle_verified`, `memory_candidate_bundle_failed`, or
`memory_candidate_bundle_incomplete`, but none of those statuses is commit
readiness, PR readiness, matrix authority, finalizer authority, PR metadata
authority, ledger authority, glow authority, daemon authority, or federation
consensus.

The normal landing sequence remains bootstrap, validation, matrix, pre-commit
finalizer, commit, post-commit/pr-metadata finalizer, PR metadata guard, and PR
metadata creation under the authoritative tools.

## Candidate verification is not ledger writing

The verifier reads candidate bundle bytes and reports structural consistency. It
does not create ledger entry ids, append ledger files, seal a chain, validate a
parent chain as active history, choose storage paths, or assert that a candidate
receipt exists in `/ledger`.

## Candidate verification is not glow archiving

The verifier reads candidate glow item metadata and reports structural
consistency. It does not copy files, retain evidence, publish archive records,
choose archive storage, disclose evidence externally, or assert that a candidate
item exists in `/glow`.

## SentientOS mount relation

- `/ledger`: candidate verification only; no ledger write.
- `/glow`: candidate verification only; no archive write.
- `/pulse`: future consumer of stored history; inactive here.
- `/daemon`: future consumer of pulse/recommendation context; inactive here.
- `/vow`: canonical constraints bounding verification interpretation and
  forbidden inference.

## Future activation requirements

All future activation requirements remain future-only, unmet, and inactive:
explicit ledger writer implementation, explicit glow archiver implementation,
explicit storage path policy, explicit retention policy, explicit digest
verification policy, explicit parent-chain validation policy, explicit operator
consent, explicit finalizer/guard non-bypass invariant, explicit pulse watcher
contract, explicit daemon action contract, explicit federation drift consensus
rule, explicit vow digest constraint check, tests proving no readiness authority,
and docs marking active behavior.

## Non-authority posture

The verifier is read-only, metadata-only, and verifier-only. It does not write
ledger, archive glow, modify memory, watch files, poll state, rerun commands,
decide readiness, bypass the finalizer, bypass the PR metadata guard, authorize
commit, authorize PR creation, trigger a daemon, create tasks, schedule tasks,
send alerts, train or modify models, or establish federation consensus.
