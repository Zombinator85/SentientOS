# Codex Workcell Storage Policy Contract

The Codex Workcell Storage Policy Contract is a deterministic, metadata-only contract for future `/ledger` and `/glow` storage implementations. It defines storage path policy, retention policy, digest verification policy, parent-chain validation policy, and vow-bound adoption requirements without performing storage work.

This contract is not a writer. It does not activate memory, write ledger entries, archive glow evidence, mutate memory, watch files, poll state, run commands, schedule tasks, trigger daemon action, decide readiness, authorize commit, authorize PR metadata, create PRs, establish federation consensus, or train or modify models.

## Relation to earlier workcell layers

- The memory contract defines future ledger and glow schemas; this storage policy defines where and under which review constraints future writers may store those schemas.
- The memory candidate bundle proposes candidate records; this contract does not accept, persist, or apply those candidates.
- The memory candidate verifier checks candidate shape; this contract does not turn verification into readiness or storage authority.
- The memory activation preflight exposes missing storage path, retention, digest, and parent-chain policies as future gaps; this contract supplies deterministic policy metadata but still leaves active storage blocked.
- The vow boundary contract defines the canonical vow digest and forbidden inference catalog; this contract requires that digest for future storage adoption.
- The vow alignment attestation binds supplied reports to the vow digest; this contract records whether that attestation was supplied but does not adopt it as active authority.

## `/ledger` path policy

Future ledger writers are limited to policy-only path patterns under `/ledger/codex/workcell/` keyed by commit SHA, PR number, or canonical vow digest. Ledger entries require source digest, parent-chain validation, vow digest, finalizer/guard non-bypass context, and operator consent.

Forbidden ledger paths include absolute host paths outside `/ledger`, hidden backdoor paths, temp paths as canonical ledger storage, network paths, provider-specific opaque paths, and paths missing digest or commit/PR lineage. Forbidden write modes include appending without parent digest, overwriting without a prior receipt, writing without vow or source digest, writing without finalizer/guard context, and writing as readiness authority.

## `/glow` path policy

Future glow archivers are limited to policy-only path patterns under `/glow/codex/workcell/` keyed by commit SHA, PR number, or canonical vow digest, with review markdown under a commit-scoped review path. Glow archives require source digest, related ledger context, vow digest, retention hint, and operator consent.

Forbidden glow paths include absolute host paths outside `/glow`, hidden backdoor paths, temp paths as canonical glow archive, network paths, provider-specific opaque paths, archive paths missing source digest, and archive paths missing vow digest. Forbidden archive modes include archiving without source digest, ledger context, vow digest, retention hint, or treating the archive as readiness authority or model-training data.

## Digest verification policy

The contract declares future-only digest requirements for raw byte SHA-256 input digests, source artifact digests, canonical vow digest, candidate bundle digest, candidate verifier digest, preflight digest, ledger entry parent-link digests, and glow item archive-context digests. These records are policy-only and do not verify or write anything by themselves.

## Parent-chain validation policy

The contract requires future active writers to carry parent entry IDs and parent entry digests after initial entries, require prior receipts before overwrite, block active writes on missing parent chains or parent digest mismatches, and never treat parent-chain validation as readiness authority.

## Retention policy

The contract defines policy-only retention classes for landing receipts, matrix receipts, finalizer receipts, PR guard receipts, evidence archives, doctrine archives, vow boundaries, and storage policy records. It does not delete, expire, archive, or move files.

## Path scope policy

The contract scopes future active storage to `/ledger` and `/glow`, forbids absolute host paths, network paths, hidden backdoor paths, and temp paths as canonical storage, and requires digest lineage and vow digest lineage. Path scope records are metadata only.

## Vow adoption relationship

When supplied, vow boundary and vow alignment inputs are summarized by raw-byte digest, byte size, and selected canonical digest metadata. If they are omitted, vow adoption remains future-only and unmet. Supplying these inputs does not perform adoption, activate storage, or authorize any write.

## Why active storage remains blocked

Active storage remains blocked because the contract intentionally reports no active writer implementation, no operator consent, no active storage harness, no active write tests, no finalizer/guard runtime binding, and no federation consensus. `active_storage_allowed_now` remains false.

## Mount alignment

- `/ledger`: future consumer of ledger storage policy; inactive here.
- `/glow`: future consumer of glow storage policy; inactive here.
- `/vow`: canonical digest required for future storage adoption.
- `/pulse`: future consumer of stored history; inactive here.
- `/daemon`: future consumer of pulse and recommendation context; inactive here.

## Future activation requirements

Future activation requires explicit active ledger writer implementation, active glow archiver implementation, storage path enforcement, retention enforcement, digest verification enforcement, parent-chain validation enforcement, operator consent, finalizer/guard runtime binding, pulse watcher contract, daemon action contract, federation drift consensus rule, tests proving no readiness authority, and docs marking active behavior. All are future-only, unmet, and inactive in this contract.

## Non-authority posture

The storage policy contract is read-only, metadata-only, and policy-only. It does not activate memory, write `/ledger`, archive `/glow`, modify memory, watch files, poll state, rerun commands, decide readiness, bypass the finalizer, bypass the PR metadata guard, authorize commit, authorize PR creation, trigger daemons, create tasks, schedule tasks, send alerts, train or modify models, or establish federation consensus.

## Storage policy verifier boundary

See [Codex Workcell Storage Policy Verifier](codex_workcell_storage_policy_verifier.md) for the metadata-only structural verifier for storage policy contracts. Its verification status is not readiness authority and it does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, schedule tasks, or bypass finalizer/PR metadata guard requirements.
