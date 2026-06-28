# Codex Workcell Storage Operator Consent Request Contract

The Codex Workcell Storage Operator Consent Request Contract is a deterministic,
metadata-only contract for the future explicit operator consent artifact that
would be required before active `/ledger` writes or `/glow` archival. It defines
request shape, evidence, scope, digest bindings, lifetime, revocation, and denial
rules only.

This contract is not consent. It does not collect operator approval, imply
operator approval, activate memory, bind runtime authority, write ledger entries,
archive glow evidence, mutate memory, watch files, poll state, schedule work,
trigger daemon action, decide readiness, authorize commits, authorize PR metadata,
create PRs, establish federation consensus, or train or modify models.

## Relationship to runtime authority verification

The storage runtime authority boundary contract and verifier prove that runtime
bindings remain absent and active storage is blocked. This operator consent
request contract covers the separate missing boundary: what a future explicit
operator consent artifact must contain. Runtime authority evidence can be a
future input to consent, but runtime authority evidence is not itself consent.

## Future explicit consent evidence

A future consent artifact must explicitly reference operator identity, operator
timestamp, operator scope statement, canonical vow digest, storage policy contract
and verifier digests, transaction plan and verifier digests, execution dossier and
verifier digests, runtime authority contract and verifier digests, pre-commit
finalizer receipt, PR metadata finalizer receipt, and PR metadata guard receipt.
Missing or ambiguous evidence keeps active storage denied.

## Scope and mounts

Future consent may only scope active storage to `/ledger` and `/glow`, and ledger
writes and glow archival must each be explicitly allowed. `/vow`, `/pulse`, and
`/daemon` are forbidden as active storage targets here. Host absolute paths,
network paths, temporary paths as canonical targets, and hidden backdoor paths are
also forbidden.

Mount alignment remains narrow:

- `/ledger`: future consent scope target; no ledger write here.
- `/glow`: future consent scope target; no archive write here.
- `/vow`: canonical digest required for future consent binding.
- `/pulse`: future watcher boundary; consent here does not activate it.
- `/daemon`: future action boundary; consent here does not activate it.

## Digest binding requirements

A future consent artifact must bind sha256 digests for the canonical vow, storage
policy, transaction plan, execution dossier, and runtime authority evidence. This
contract may summarize supplied report digests, but digest binding is not
performed here and supplied reports do not imply consent.

## Lifetime, renewal, revocation, and denial

Future consent must include expiration and revocation terms. Renewal is required
for a new vow digest, new storage policy, new transaction plan, or changed mount
scope. Revocation must block future writes and archives, must not delete existing
receipts, and must create a future revocation receipt. The default without
explicit consent is `deny_active_storage`.

## Forbidden implied consent

Finalizer ready-to-commit status, PR metadata guard readiness, daemon
recommendations, supplied reports, federation state, and this schema do not imply
operator consent. Remote or daemon consent is not accepted for this boundary;
future operator consent must be explicit and scoped.

## Active storage remains blocked

The contract records that operator consent is absent, runtime binding is not
performed, active storage is not allowed now, execution is not performed, writes
are not performed, archives are not performed, and memory mutation is not
performed. Blocking gaps include missing operator consent, operator identity,
consent timestamp, consent scope, digest bindings, expiration, revocation terms,
explicit ledger write allowance, explicit glow archive allowance, and runtime
authority binding.

## Reviewer URL hygiene

Reviewer URL hygiene is separate from runtime behavior. The contract records that
the OpenAI-hosted SentientOS repository URL is expected to be absent and that the
correct repository URL is `https://github.com/Zombinator85/SentientOS.git`, but
repository grep validation is performed by the landing task, not by this metadata
contract.

## Future activation requirements

Future activation remains unmet and inactive until explicit operator identity,
explicit operator consent, timestamp, expiration, revocation, digest bindings,
active ledger writer implementation, active glow archiver implementation,
finalizer and PR metadata guard runtime binding implementations, storage path
enforcement, retention enforcement, digest verification enforcement,
parent-chain validation enforcement, no-readiness-authority tests, and active
behavior docs exist.

## Non-authority posture

The contract is read-only, metadata-only, and contract-only. It does not collect
or imply consent, bind runtime authority, activate memory, write ledger entries,
archive glow evidence, modify memory, watch files, poll state, rerun commands,
decide readiness, bypass finalizer or PR metadata guard, authorize commit or PR
creation, trigger daemons, create or schedule tasks, send alerts, train or modify
models, or establish federation consensus.

## Storage operator consent request verifier boundary

See [Codex Workcell Storage Operator Consent Request Verifier](codex_workcell_storage_operator_consent_verifier.md) for the deterministic metadata-only verifier for the future operator consent request shape. The verifier does not collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, authorize PR metadata, or establish federation consensus.

## Storage operator consent request packet boundary

See [Codex Workcell Storage Operator Consent Request Packet](codex_workcell_storage_operator_consent_request_packet.md) for the deterministic metadata-only future request packet shape. The packet does not present a request, collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, authorize PR metadata, create PRs, or establish federation consensus.

## Operator consent request packet verifier boundary

The [Codex workcell storage operator consent request packet verifier](codex_workcell_storage_operator_consent_request_packet_verifier.md) is a deterministic metadata-only structural check for request packet JSON. It does not present a request, collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger `/daemon`, decide readiness, or replace finalizer/PR metadata guard authority.

## Storage operator consent response artifact boundary

The [Codex Workcell Storage Operator Consent Response Artifact Contract](codex_workcell_storage_operator_consent_response_contract.md) defines only the future response artifact schema for explicit `/ledger` and `/glow` consent. It does not create a response artifact, collect or imply consent, bind runtime authority, activate memory, write ledger entries, archive glow evidence, render UI, send messages, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, or create PRs.

## Storage operator consent response verifier boundary

The [Codex Workcell Storage Operator Consent Response Artifact Verifier](codex_workcell_storage_operator_consent_response_verifier.md) is a deterministic metadata-only structural verifier for the future response artifact contract. It creates no response artifact, collects or implies no consent, grants no readiness, storage, ledger, glow, daemon, federation, UI, message, scheduler, commit, PR metadata, or runtime authority, and leaves active storage blocked.
