# Household Presence Camera Operator Grant Renewal Request Packet

The Household Presence Camera Operator Grant Renewal Request Packet is a deterministic, metadata-only review layer. It consumes camera operator review trend ledger evidence and upstream decision/review metadata to describe which explicit operator grant renewal or proof-refresh requests should be reviewed next.

It is not live hardware access. It does not open cameras, access microphones, inspect hardware, call media APIs, process images/video/audio, store media, run live adapters, call providers, call networks, call subprocesses from library code, produce speaker output, or create external disclosure.

A request packet is not consent. It does not create, infer, renew, approve, apply, or persist an operator grant. Every successful record states `request_grants_operator_consent: false` and `request_renews_operator_grant: false`.

A request packet is not live readiness. Dry-run history can request operator review for dry-run continuation, but the packet states `request_enables_dry_run_continuation: false`, `request_enables_live_capture: false`, and `request_confers_live_readiness: false`.

## Relationship to upstream layers

1. The capture review decision ledger records operator-review decisions.
2. The operator review trend ledger groups repeated decisions and stale review evidence into metadata-only trends.
3. This renewal request packet translates those trends into explicit renewal/proof-refresh requests.
4. Any proof repair or explicit operator grant renewal happens outside this packet.
5. Operators rerun the capture review packet after refresh.
6. A later dry-run-only continuation gate may consider the refreshed evidence.
7. Future live-candidate review requires explicit separate confirmation.

The packet references the capture authorization envelope, capture denial ledger, capture review packet, capture review decision ledger, camera policy chain, zone config, dry-run proof, and disabled-capture adapter contract only by digest/metadata. It never bypasses those layers.

## Request reasons and refresh types

Request reasons include repeated operator grant renewal pressure, expired or missing grant pressure, dry-run repair pressure, policy-chain proof repair, zone-config repair, disabled-capture boundary repair, repeated capture denial pressure, stale review refresh, stale trend refresh, dry-run continuation review, future live review deferral, mixed-scope operator review, and no-op diagnostics when explicitly allowed.

Requested refresh types include operator grant renewal, dry-run proof refresh, policy-chain proof refresh, zone-config refresh, disabled-capture boundary refresh, capture review packet rerun, decision ledger review, trend ledger review, denial history review, and future-live deferral confirmation.

## Safe and forbidden next actions

Safe next actions are request or inspection labels only: operator review required, request operator grant renewal, request dry-run proof refresh, request policy-chain proof refresh, request zone-config refresh, request disabled-capture boundary refresh, rerun capture review packet, inspect decision history, inspect trend history, sustain capture denial, defer future live review, or no action allowed.

Every successful packet includes forbidden next steps including opening a camera, attempting capture, enabling live capture/recording, storing or attaching media, bypassing authorization/denial/review/trend/policy/zone/disabled-capture/dry-run layers, inferring consent from trends or the request, converting the request to a grant or live readiness, enabling speaker output, or enabling external disclosure.

## Staleness and scope behavior

Stale trend evidence blocks or warns according to policy. Stale review evidence blocks or warns according to policy. Missing trend ledgers block. Missing decision ledger or review packet digests block unless trend-only diagnostic packets are explicitly allowed. Mixed scope blocks by default; when mixed-scope diagnostic summaries are explicitly allowed, output is ready with warnings and never merges scope into authority.

## No media, no hardware, no live runtime

Fixtures and runtime inputs are metadata only: no images, audio, video, thumbnails, screenshots, base64 media, raw transcripts, or real hardware serials. The library is deterministic and contains no provider/network/GitHub/subprocess/live-camera behavior.
