# Codex Workcell Storage Operator Consent Request Packet Verifier

The Codex workcell storage operator consent request packet verifier is a deterministic, metadata-only structural verifier for a supplied operator consent request packet JSON. It reads the packet and optional context reports, records raw-byte SHA-256 input summaries, and emits a verification report about packet shape only.

The request packet assembles a future operator-facing consent request shape. The request packet verifier checks that shape. Neither presents a request, renders UI, sends a message, delivers externally, collects a response, implies consent, binds runtime authority, activates memory, writes ledger entries, archives glow evidence, mutates memory, triggers daemon action, schedules tasks, establishes federation consensus, or grants readiness.

## Structural checks

The verifier checks that the packet declares metadata-only packet posture, keeps `consent_request_not_presented`, `consent_not_collected`, and `consent_not_implied` true, keeps `operator_consent_present`, active storage, execution, writes, archives, and memory mutation false, and preserves an evidence digest packet with all supported evidence roles.

It also checks the operator request template, required empty operator response fields, consent scope statement, digest binding statement, lifetime statement, revocation statement, denial statement, authority boundary statement, blocking gap IDs, reviewer hygiene metadata, future activation requirements, mount alignment, and non-authority posture.

## Status is not authority

`storage_operator_consent_request_packet_verified` means only that the supplied packet has the expected structural metadata. It is not consent, presentation, response capture, commit readiness, PR readiness, matrix authority, finalizer authority, PR metadata authority, ledger authority, glow authority, daemon authority, storage activation, runtime authority binding, or permission to run an active writer.

Finalizer readiness, PR metadata guard readiness, daemon recommendations, federation state, and supplied reports do not imply operator consent. Operator response fields must remain empty here because this layer is before any explicit presentation and response capture mechanism. Active storage remains blocked until separate future mechanisms collect explicit operator identity, timestamp, scope, digest acknowledgements, expiration, revocation terms, runtime binding, and enforcement evidence.

## Boundaries

The verifier is not a writer, archiver, daemon action, scheduler, consent collector, UI renderer, message sender, external delivery system, watcher, poller, task creator, alerting system, model trainer, federation consensus system, or runtime binder. Reviewer URL hygiene remains documentation/review validation performed by the landing task, not runtime behavior.

## Mount relation

- `/ledger`: operator consent request packet verification only; no ledger write.
- `/glow`: operator consent request packet verification only; no archive write.
- `/vow`: canonical digest evidence for future consent binding.
- `/pulse`: future watcher boundary; the packet verifier does not activate it.
- `/daemon`: future action boundary; the packet verifier does not activate it.

## Future activation requirements

Future active behavior requires explicit operator identity capture, explicit consent response capture, request presentation, timestamp capture, expiration and revocation policy, digest acknowledgements, active ledger/glow implementations, finalizer and PR guard runtime binding, storage path enforcement, retention enforcement, digest verification enforcement, parent-chain validation enforcement, tests proving no readiness authority, and docs marking active behavior.

## Non-authority posture

All verifier posture flags are true: read-only, metadata-only, verifier-only, no request presentation, no UI rendering, no messages, no external delivery, no consent collection or implication, no runtime authority binding, no memory activation, no ledger write, no glow archive, no memory mutation, no file watching, no polling, no command reruns, no readiness decision, no finalizer or PR guard bypass, no commit or PR authorization, no daemon trigger, no task creation, no scheduling, no alerts, no model training/modification, and no federation consensus.
