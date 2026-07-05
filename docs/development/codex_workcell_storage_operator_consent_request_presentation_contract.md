# Codex Workcell Storage Operator Consent Request Presentation Boundary Contract

The Codex workcell storage operator consent request presentation boundary contract is a deterministic, metadata-only, future-only contract for the missing authority layer between a consent request packet and any real operator-facing presentation. It defines the requirements, surfaces, denied inferences, missing gaps, mount alignment, and non-authority posture that must exist before any future system may present a storage operator consent request packet.

This contract does not present a request, render UI, send messages, deliver externally, create a response artifact, collect a response, collect or imply consent, bind runtime authority, activate memory or storage, write `/ledger`, archive `/glow`, mutate memory, watch files, poll state, run commands, call networks, invoke providers, schedule tasks, create tasks, send alerts, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, create PRs, establish federation consensus, or train or modify models.


See [Codex Workcell Storage Operator Consent Request Presentation Verifier](codex_workcell_storage_operator_consent_request_presentation_verifier.md) for the deterministic metadata-only verifier for this presentation boundary; verifier status remains structure-only and does not prove presentation or consent.

## Ladder position

- The storage operator consent request contract defines the future request requirements.
- The request verifier verifies that request contract shape without collecting consent.
- The request packet packages future operator-facing request metadata but does not present it.
- The packet verifier verifies packet structure but does not prove presentation.
- The response artifact contract defines a future response schema but does not create a response artifact.
- The response verifier verifies that schema boundary without proving a response exists.
- The evidence dossier inventories consent-design evidence but does not prove an operator saw anything.
- The evidence dossier verifier verifies that dossier boundary without closing the presentation gap.
- This presentation boundary contract names the future-only presentation authority requirements and still performs no presentation.

## Why packet and evidence existence are not presentation

A request packet existing is not presentation because no explicit presentation mechanism, channel authorization, operator identity target, digest-bound display, cancellation path, audit receipt path, UI authority, message authority, external delivery authority, response artifact creation authority, response collection authority, consent collection authority, runtime binding, ledger writer, or glow archiver is active. A verified packet is still only verified metadata.

Complete or verified consent-design evidence is not presentation either. Evidence completeness can show that the design ladder is internally consistent, but it cannot show that an operator saw the request, reviewed the digest inventory, acknowledged ledger or glow implications, selected expiration terms, accepted revocation terms, signed a response, or granted consent.

## Presentation authority remains separate

Presentation authority is separate from UI rendering, message delivery, external delivery, response artifact creation, response collection, consent collection, runtime binding, and active storage. Each of those actions requires explicit future authority and must remain inactive here.

Finalizer readiness, PR metadata guard readiness, matrix passage, daemon recommendations, federation state, storage policy evidence, and runtime authority contracts do not imply presentation authority. They are review, evidence, policy, or boundary signals, not operator-facing presentation permission.

Operator silence, notification delivery, local file creation, message delivery, or a displayed copy cannot imply consent. Consent requires a future explicit response path, identity boundary, scope statement, digest acknowledgement, expiration boundary, revocation boundary, and response status boundary.

## Active storage remains blocked

Active storage remains blocked because request presentation is missing, consent collection is missing, response artifact creation is missing, runtime binding is missing, and active `/ledger` and `/glow` writer implementations are not authorized by this metadata contract.

## Reviewer URL hygiene

Reviewer URL hygiene remains separate from runtime behavior. The contract records that `https://github.com/Zombinator85/SentientOS.git` is the correct repository URL and that the legacy bad OpenAI repository URL is expected absent, but grep validation is performed by the landing task rather than by this contract.

## SentientOS mount alignment

- `/ledger`: future operator consent presentation receipt chain only; no ledger write.
- `/glow`: future presentation evidence archive only; no archive write.
- `/vow`: canonical digest context for future presentation and consent constraints.
- `/pulse`: future presentation freshness or drift signal boundary; not activated.
- `/daemon`: future bounded presentation repair recommendation boundary; not activated and no daemon action.

## Future activation requirements

Future activation requires an explicit presentation mechanism, presentation channel authorization, operator identity targeting, request packet digest binding, evidence dossier digest binding, vow digest binding, operator-facing scope display, ledger and glow allow questions, digest acknowledgement display, expiration policy display, revocation terms display, no-implied-consent and no-readiness-authority notices, response artifact path, response collection boundary, operator cancellation path, presentation audit receipt path, UI/message/external delivery authority when used, response artifact creation authority, response collection authority, consent collection authority, runtime authority binding implementation, active ledger writer implementation, active glow archiver implementation, tests proving no presentation readiness authority, and docs marking active behavior.

## Non-authority posture

The presentation boundary contract is metadata-only, contract-only, and future-only. It is not a presentation runner, UI renderer, message sender, external delivery system, response artifact creator, response collector, consent collector, runtime authority, memory writer, ledger writer, glow archiver, watcher, scheduler, executor, daemon action, task creator, alerting system, model trainer, reinforcement learning system, readiness authority, commit authority, PR authority, or federation consensus mechanism.
