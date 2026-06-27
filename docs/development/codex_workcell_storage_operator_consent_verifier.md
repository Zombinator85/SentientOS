# Codex Workcell Storage Operator Consent Request Verifier

The Codex Workcell Storage Operator Consent Request Verifier is a deterministic,
metadata-only verifier for the storage operator consent request contract. It reads
a supplied contract JSON and optional context reports, computes input byte sizes
and sha256 digests, and emits a structural verification report.

The consent request contract defines the future request shape. The verifier
checks that shape. Neither artifact is operator consent.

## Structural checks

The verifier checks that the contract remains metadata-only, contract-only, and
shape-only; that consent is not collected or implied; that operator consent is
absent; that runtime binding, active storage, execution, writes, archives, and
memory mutation remain absent; that all required schema and evidence IDs are
present; that schema rows are future-only, inactive, and currently unsatisfied;
that scope is exactly `/ledger` and `/glow`; that `/vow`, `/pulse`, `/daemon`,
host absolute paths, network paths, temporary canonical paths, and hidden
backdoor paths are forbidden; that sha256 digest binding policy, lifetime,
revocation, denial, authority-boundary, activation-gap, future-requirement, and
non-authority posture sections remain intact.

`verification_status` is only contract-structure status. It is not operator
consent, storage readiness, commit readiness, PR readiness, finalizer authority,
PR metadata authority, ledger authority, glow authority, daemon authority,
runtime authority binding, or permission to run an active writer.

## No implied consent

Finalizer readiness, PR metadata guard readiness, daemon recommendations,
federation state, supplied reports, and verifier output do not imply consent.
Future operator consent must be explicit, local, scoped, timestamped, revocable,
expiring, and bound to the required vow, policy, transaction-plan, execution dossier, runtime-authority, finalizer, and guard evidence digests.

## Active storage remains blocked

This verifier is not a writer, archiver, scheduler, daemon action, consent
collector, runtime binder, readiness decider, watcher, task creator, alerting
system, model trainer, memory mutator, or federation consensus mechanism. It
performs no `/ledger` write, no `/glow` archive, no memory activation, no daemon
action, and no runtime binding.

## Reviewer URL hygiene

Reviewer URL hygiene remains separate from runtime behavior. The verifier reports
that the OpenAI-hosted SentientOS repository attribution is expected to be absent
and that `https://github.com/Zombinator85/SentientOS.git` is the correct clone
URL, but repository grep validation is performed by the landing task rather than
by the verifier.

## Mount alignment

- `/ledger`: operator consent request verification only; no ledger write.
- `/glow`: operator consent request verification only; no archive write.
- `/vow`: canonical digest required for future consent binding.
- `/pulse`: future watcher boundary; the verifier does not activate it.
- `/daemon`: future action boundary; the verifier does not activate it.

## Future activation requirements

All future activation requirements are represented as future-only, unmet, and
inactive: explicit operator identity, explicit consent capture, timestamp,
expiration, revocation, canonical vow digest binding, storage policy binding,
transaction plan binding, execution dossier binding, runtime authority binding,
active ledger writer implementation, active glow archiver implementation,
finalizer and PR metadata guard runtime binding implementations, storage path
enforcement, retention enforcement, digest verification enforcement, parent-chain
validation enforcement, no-readiness-authority tests, and active-behavior docs.

## Non-authority posture

The verifier is read-only, metadata-only, and verifier-only. It does not collect
or imply consent, bind runtime authority, activate memory, write ledger entries,
archive glow evidence, modify memory, watch files, poll state, rerun commands,
decide readiness, bypass finalizer or PR metadata guard, authorize commits or PR
creation, trigger daemons, create or schedule tasks, send alerts, train or modify
models, or establish federation consensus.
