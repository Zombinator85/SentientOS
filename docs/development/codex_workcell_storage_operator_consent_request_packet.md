# Codex Workcell Storage Operator Consent Request Packet

The Codex Workcell Storage Operator Consent Request Packet is a deterministic,
metadata-only packet builder for a future operator-facing consent request shape.
It assembles supplied consent, runtime authority, storage, vow, and dossier
evidence into a compact packet with source SHA-256 digests, byte sizes, request
scope, future response fields, and explicit non-authority posture.

This packet is still not consent. It does not present a request to an operator,
render UI, send a message, deliver an external notification, collect a response,
imply approval, bind runtime authority, activate memory, write `/ledger`, archive
`/glow`, mutate memory, watch files, poll state, schedule work, create tasks,
trigger daemon action, decide readiness, authorize commits, authorize PR metadata,
create PRs, establish federation consensus, or train or modify models.

## Contract, verifier, and packet distinction

- The [storage operator consent request contract](codex_workcell_storage_operator_consent_contract.md)
  defines the future consent schema and required evidence policy.
- The [storage operator consent request verifier](codex_workcell_storage_operator_consent_verifier.md)
  verifies that the contract remains future-only and non-authoritative.
- This request packet assembles the future request packet shape from supplied
  evidence summaries and verified consent-policy artifacts, while keeping every
  operator-response field empty, false, unavailable, and not collected.

## Evidence digest packet

For each supported optional input, the packet records whether it was supplied, the
source path, SHA-256 digest, byte size, JSON readability, detected report ID when
present, evidence role, and relevant status or digest when derivable. Omitted
inputs remain explicit `provided: false` records with no digest and no byte size.
The builder never runs other builders or verifiers; it only reads explicitly
supplied JSON files.

## Future operator request template

The operator request template is metadata only. It is marked
`template_not_presented`, `response_not_collected`, `no_message_sent`,
`no_ui_rendered`, and `no_external_delivery`. The future requested scope is only
`/ledger` and `/glow`, with explicit permissions for ledger writing and glow
archiving. `/vow`, `/pulse`, `/daemon`, host absolute paths, network paths,
temporary paths as canonical targets, and hidden backdoor paths remain forbidden.
The default without a future explicit response is `deny_active_storage`.

## Required future operator response fields

Future fields such as operator identity, timestamp, scope statement, consent
expiration, revocation acknowledgement, digest acknowledgements, finalizer/guard
receipt acknowledgements, daemon/federation no-implied-consent acknowledgements,
response completeness, and consent artifact creation all remain `null` or `false`
in this packet. Active storage therefore remains blocked.

## No implied consent from evidence or readiness

Supplied reports, finalizer ready-to-commit status, PR metadata guard readiness,
daemon recommendations, and federation state do not imply consent. Future consent
must be explicit, scoped, time-bound, revocable, digest-bound, and operator-owned.
This packet records missing operator response, missing identity, missing timestamp,
missing scope statement, missing explicit ledger/glow allowances, missing
expiration, missing revocation terms, missing digest acknowledgements, and missing
runtime authority binding as blocking gaps.

## Mount alignment

- `/ledger`: future requested consent scope; no ledger write happens here.
- `/glow`: future requested consent scope; no archive write happens here.
- `/vow`: canonical digest evidence for future consent binding.
- `/pulse`: future watcher boundary; this packet does not activate it.
- `/daemon`: future action boundary; this packet does not activate it.

## Reviewer URL hygiene

Reviewer URL hygiene remains separate from runtime behavior. The packet records
that `https://github.com/` + `OpenAI/` + `SentientOS.git` is expected to be absent and that
`https://github.com/Zombinator85/SentientOS.git` is the correct repository URL,
but repository grep validation is performed by the landing task, not by this
metadata packet.

## Future activation requirements

Future activation remains unmet and inactive until there is explicit operator
identity capture, consent response capture, consent request presentation,
timestamp capture, expiration and revocation policy, canonical vow/storage
policy/transaction plan/execution dossier/runtime authority digest
acknowledgement, active ledger writer and glow archiver implementations,
finalizer and PR metadata guard runtime binding implementations, storage path and
retention enforcement, digest verification, parent-chain validation, tests proving
no readiness authority, and docs marking active behavior.

## Non-authority posture

The packet is read-only, metadata-only, and packet-only. It does not present a
request, collect or imply consent, bind runtime authority, activate memory, write
ledger entries, archive glow evidence, modify memory, watch files, poll state,
rerun commands, decide readiness, bypass the finalizer, bypass the PR metadata
guard, authorize commit, authorize PR creation, trigger daemons, create or
schedule tasks, send alerts, train or modify models, or establish federation
consensus.
