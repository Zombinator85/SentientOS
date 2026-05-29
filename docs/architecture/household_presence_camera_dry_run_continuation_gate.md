# Household Presence Camera Dry-Run-Only Continuation Gate

The Household Presence camera dry-run-only continuation gate is a deterministic,
metadata-only review layer. It consumes the capture review packet, capture review
decision ledger, operator review trend ledger, and operator grant renewal request
packet to decide whether later **non-live** dry-run review workflows may remain
available.

The gate exists because dry-run history can accumulate review, trend, denial,
staleness, and grant-renewal pressure. Reviewers need one packet that explains
whether continuation remains safe as metadata review only, or whether the next
human action is repair, review, renewal, deferral, or denial sustainment.

## Non-authority boundary

This gate is not live hardware access. It does not open cameras, inspect devices,
call operating-system media APIs, execute capture adapters, process media, store
raw payloads, invoke providers, or call external services. It evaluates local JSON
metadata only.

The gate does not execute dry-run capture. A `continue_dry_run_only` decision
means the metadata review trail may continue as dry-run-only review; it is not a
runtime invocation and does not start any adapter.

The gate is not operator consent and is not grant renewal. Renewal request packet
evidence can require a later explicit grant-renewal proof, but this gate cannot
convert that request into a grant. Trend history cannot infer consent. Review
history cannot infer consent.

The gate is not live readiness. It never converts dry-run continuation, future
live review deferral, request history, or trend history into live capture
permission. Every successful record keeps live capture, live hardware, raw media
storage, speaker output, external disclosure, grant renewal, consent, capture
authorization, and dry-run execution flags closed.

## Relationship to upstream evidence

1. **Capture review packet** — provides the reviewed camera capture metadata that
   must be compatible with dry-run-only or operator-review dry-run continuation.
   Missing, not-ready, stale, or live-only review packet evidence blocks or warns
   according to policy.
2. **Capture review decision ledger** — records prior review decisions. The gate
   requires ready or ready-with-warnings decision evidence and rejects unsafe
   continuation blockers.
3. **Operator review trend ledger** — summarizes repeated decision patterns. The
   gate accepts trends only as metadata; trends cannot infer operator consent or
   live readiness.
4. **Operator grant renewal request packet** — translates trend pressure into
   request metadata. Any operator-grant-renewal requirement blocks continuation
   until a later explicit proof layer exists. Proof-refresh requirements block by
   default unless diagnostic continuation review is explicitly allowed.
5. **Capture authorization envelope and denial ledger** — optional digests may be
   carried forward as evidence. They are never bypassed; unresolved denials above
   policy threshold block continuation.
6. **Disabled capture adapter contract, policy chain, and zone configuration** —
   optional digests may be carried forward. Refresh requirements for these
   surfaces block by default.

## Gate statuses

The gate emits deterministic statuses including ready, ready-with-warnings,
missing upstream evidence blockers, upstream-not-ready blockers, operator grant
required, proof refresh required, unresolved denials, scope mismatch, stale
review/trend/request, future-live-only evidence, media payload, speaker boundary,
external authority, invalid, and failed.

Ready statuses are metadata-only. Blocked statuses mean no continuation action is
available from this gate. Warning status means the output is diagnostic and does
not merge scopes or grant authority.

## Gate decisions

Decisions are limited to metadata review posture:

- `continue_dry_run_only`
- `defer_dry_run_continuation`
- `require_operator_review`
- `require_operator_grant_renewal`
- `require_dry_run_proof_refresh`
- `require_policy_chain_proof_refresh`
- `require_zone_config_refresh`
- `require_disabled_capture_boundary_refresh`
- `require_capture_review_packet_rerun`
- `require_decision_ledger_review`
- `require_trend_ledger_review`
- `require_renewal_request_review`
- `sustain_capture_denial`
- `defer_future_live_review`
- `reject_continuation_request`

No decision authorizes capture, grant renewal, consent inference, live readiness,
speaker output, external disclosure, or runtime dry-run execution.

## Safe next actions

Safe next actions are constrained to metadata review work: no action,
continue dry-run-only review, operator review, request grant renewal, request
proof or policy/zone/disabled-boundary refresh, rerun the capture review packet,
inspect decision/trend/request history, sustain capture denial, or defer future
live review.

## Forbidden next steps

Every successful output includes forbidden next steps such as opening the camera,
attempting capture, enabling live capture or recording, storing raw media,
attaching media payloads, bypassing the authorization envelope, denial ledger,
review packet, decision ledger, trend ledger, renewal request packet, policy
chain, zone config, disabled capture boundary, or dry-run boundary, inferring
operator consent from the gate/trends/renewal request, converting renewal
requests to grants, converting dry-run gate output to live readiness or live
capture permission, enabling speaker output, or enabling external disclosure.

## Staleness behavior

Review staleness blocks by default. Trend and request staleness warn by default.
Policy can change each staleness mode to `block` or `warn`, but warning output
remains metadata-only and confers no runtime authority.

## Scope mismatch behavior

Scope mismatch between review packet, decision ledger, trend ledger, renewal
request packet, source candidate, or requested mode blocks by default. A policy
can allow mixed-scope diagnostic summaries, but those summaries are
ready-with-warnings and never merge scope into authority.

## Unresolved denial behavior

Unresolved denials above the policy threshold block continuation. Sustained
denial history remains sustained; it is not transformed into continuation or live
readiness.

## No media, no hardware, no live runtime

Fixtures and CLI inputs are metadata-only JSON. They contain no images, audio,
video, thumbnails, screenshots, raw transcripts, or real hardware serials. The
library contains no subprocess, provider, network, or media stack invocation and
never executes camera daemons, live adapters, speaker/talkback bridges, or
embodiment runtime components.

## Future sequence

1. Capture review decision ledger.
2. Operator review trend ledger.
3. Operator grant renewal request packet.
4. Dry-run-only continuation gate.
5. Explicit proof repair or operator grant renewal outside this gate.
6. Rerun capture review packet.
7. Future live-candidate review only after explicit separate confirmation.

## Validation and integration

The implementation is exposed through
`scripts/build_household_presence_camera_dry_run_continuation_gate.py`, covered by
unit and CLI tests, listed in the capability registry as a metadata-only
review/gate/audit capability, represented in the reviewer proof bundle, and wired
into the work-item review packet matrix.
