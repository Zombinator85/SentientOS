# Household Presence Camera Review Chain Summary Packet

The Household Presence Camera Review Chain Summary Packet is a deterministic,
metadata-only operator review artifact. It composes already-landed camera review
chain evidence into one packet so an operator can see the current chain posture,
source digests, warning and blocker counts, stale evidence, unresolved denials,
scope state, safe next actions, and forbidden next steps without creating a new
decision or authority grant.

## Non-authority boundary

The summary packet is not live hardware access. It reads explicit local JSON
metadata supplied by the caller and does not open cameras, microphones, device
nodes, operating-system media APIs, browser capture APIs, OpenXR/Quest surfaces,
or any capture stack. It never processes image, video, audio, thumbnail,
screenshot, base64 media, raw transcript, or hardware serial payloads.

The packet does not execute dry-run capture. Dry-run continuation evidence is
summarized only as review-chain continuity metadata, and every successful record
sets `summary_executes_dry_run` to `false`.

The packet does not schedule live review and does not approve a live candidate.
Future live-candidate status remains deferred/operator-only, and every
successful record sets `summary_schedules_live_review`,
`summary_approves_live_candidate`, and `summary_confers_live_readiness` to
`false`.

The packet is not operator consent and is not grant renewal. Renewal request and
operator trend evidence may be shown as review context, but every successful
record sets `summary_grants_operator_consent` and
`summary_renews_operator_grant` to `false`.

## Relationship to upstream evidence

The summary packet links these upstream artifacts by digest and source IDs:

1. Capture review packet.
2. Capture review decision ledger.
3. Operator review trend ledger.
4. Operator grant renewal request packet.
5. Dry-run-only continuation gate.
6. Future live-candidate deferral registry.

Optional metadata links may include the capture authorization envelope digest,
capture denial ledger digest, policy-chain digest, zone-configuration digest,
and dry-run proof digest. These links are evidence references only; they are not
adoption, transport, sync, merge, apply, install, execution, consent, or live
readiness.

## Status behavior

Successful statuses are `review_chain_summary_packet_ready` and
`review_chain_summary_packet_ready_with_warnings`. Missing required chain layers
block with a layer-specific missing-evidence status. Unsafe live implications,
media payloads, speaker/talkback requests, external disclosure requests,
unresolved denials over policy threshold, stale evidence in block mode, and
scope mismatch in default policy all block.

Ready-with-warnings upstream evidence can produce a warning summary when policy
allows it. Blocked/invalid/failed upstream evidence can be summarized only as a
diagnostic warning when policy explicitly allows diagnostic summaries.

## Conclusion behavior

The summary conclusions describe review posture only:

- `review_chain_metadata_ready`
- `review_chain_ready_with_warnings`
- `review_chain_operator_review_required`
- `review_chain_operator_grant_required`
- `review_chain_proof_refresh_required`
- `review_chain_capture_review_packet_rerun_required`
- `review_chain_decision_history_review_required`
- `review_chain_trend_history_review_required`
- `review_chain_renewal_request_review_required`
- `review_chain_dry_run_gate_review_required`
- `review_chain_future_live_deferral_confirmed`
- `review_chain_future_live_remains_deferred`
- `review_chain_sustain_capture_denial`
- `review_chain_blocked_by_unresolved_denials`
- `review_chain_blocked_by_scope_mismatch`
- `review_chain_blocked_by_stale_evidence`
- `review_chain_blocked_by_unsafe_live_implication`

A conclusion does not authorize capture, renew an operator grant, infer consent,
execute dry-run capture, schedule live review, approve a live candidate, or mark
anything live-ready.

## Safe next actions

Safe next actions are operator-facing metadata actions: inspect the review chain,
inspect decision/trend/renewal/gate/deferral history, request operator grant
renewal outside this packet, request dry-run/policy/zone/disabled-boundary proof
refresh outside this packet, rerun the capture review packet, sustain capture
denial, or maintain future-live deferral. `no_action_allowed` is available for
fully blocked diagnostic contexts.

## Forbidden next steps

Every successful packet records forbidden next steps including camera opening,
capture attempts, live capture or recording enablement, raw media storage, media
attachments, dry-run execution, live review scheduling, live-candidate approval,
live-ready marking, bypassing any review-chain layer, consent inference from the
summary/chain/gate/trends/renewal request, converting renewal requests to
grants, converting dry-run gates/deferrals/summaries to live readiness or live
capture permission, speaker output, and external disclosure.

## Stale, scope, and denial behavior

Stale review, decision, trend, request, gate, and deferral evidence is counted
separately. Each stale category can block or warn according to policy, with the
default policy warning so an operator can inspect the chain without receiving
new authority.

Scope mismatch across the review packet, decision ledger, trend ledger, renewal
request packet, dry-run gate, future live deferral registry, source candidate,
and requested mode blocks by default. Mixed-scope diagnostic mode can warn, but
it never merges scopes into authority.

Unresolved denials above `max_unresolved_denials` block readiness. Sustaining a
capture denial is a safe metadata action, not an approval path.

## Future sequence

The intended future sequence remains:

1. Capture review decision ledger.
2. Operator review trend ledger.
3. Operator grant renewal request packet.
4. Dry-run-only continuation gate.
5. Future live-candidate deferral registry.
6. Review chain summary packet.
7. Explicit proof repair or operator grant renewal outside this packet.
8. Rerun capture review packet.
9. Future live-candidate review only after explicit separate confirmation in a later task.
