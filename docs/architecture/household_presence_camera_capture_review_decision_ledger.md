# Household Presence Camera Capture Review Decision Ledger

The Household Presence camera capture review decision ledger is a deterministic,
metadata-only audit surface for operator review outcomes on capture review
packets. It records whether an operator denied a request, deferred review,
requested proof repair, requested operator grant renewal, allowed only dry-run
continuation, sustained denial history, rejected a review packet, or marked a
future-live review as deferred.

## Not live hardware access

The ledger does not open cameras, microphones, browser media APIs, OS media
stacks, OpenXR/Quest surfaces, or live adapters. It reads only explicit JSON
metadata supplied by the operator or tests. It never stores images, audio,
video, thumbnails, screenshots, transcripts, base64 media, hardware serials, or
raw media payloads. Library code performs no subprocess, shell, provider,
network, GitHub, speaker, talkback, or external-disclosure action.

Every successful record explicitly keeps these boundary flags closed:

- `capture_enabled: false`
- `capture_available: false`
- `live_hardware_enabled: false`
- `raw_media_storage_enabled: false`
- `no_live_capture_performed: true`
- `speaker_output_enabled: false`
- `external_disclosure_enabled: false`

## Relationship to the capture review packet

The capture review packet aggregates prerequisite metadata for operator review.
The decision ledger is the next audit layer: it records the operator-facing
outcome for that packet, keyed by review packet id and digest. A missing review
packet blocks the ledger. A blocked, invalid, or failed review packet blocks
unsafe continuation; deny, defer, sustain-denial, reject, and repair decisions
may still be recorded because they do not enable capture.

## Relationship to authorization, denial, and disabled-capture proofs

The record keeps optional digests for the capture authorization envelope, denial
ledger, policy chain, zone configuration, and dry-run proof. These digests are
metadata anchors only. They do not issue an authorization grant, override the
denial ledger, bypass the disabled-capture adapter contract, or convert review
into live capture.

## Decision types

Supported decision types are:

- `deny_capture_request`
- `defer_review`
- `require_operator_grant_renewal`
- `require_dry_run_repair`
- `require_policy_chain_repair`
- `require_zone_config_repair`
- `require_disabled_capture_boundary_repair`
- `allow_dry_run_only_continuation`
- `mark_future_live_review_deferred`
- `sustain_denial_history`
- `reject_review_packet`

`allow_dry_run_only_continuation` is permitted only when the review packet is
ready for dry-run-only or operator review under compatible policy. It never means
live-ready. `mark_future_live_review_deferred` always stays deferred and
operator-only.

## Safe next actions

The ledger maps decisions to bounded safe next actions:

- `no_action_allowed`
- `operator_review_required`
- `renew_operator_grant`
- `repair_dry_run_proof`
- `repair_policy_chain_proof`
- `repair_zone_config`
- `repair_disabled_capture_boundary`
- `rerun_capture_review_packet`
- `continue_dry_run_only`
- `defer_future_live_review`

## Forbidden next steps

Every successful record repeats the forbidden next steps so downstream tooling
cannot confuse an audit decision with authority:

- `open_camera_now`
- `attempt_capture`
- `enable_live_capture`
- `enable_live_recording`
- `store_raw_media`
- `attach_media_payload`
- `bypass_authorization_envelope`
- `bypass_denial_ledger`
- `bypass_review_packet`
- `bypass_policy_chain`
- `bypass_zone_config`
- `bypass_disabled_capture_boundary`
- `bypass_dry_run`
- `enable_speaker_output`
- `enable_external_disclosure`

## Unresolved denial and stale review behavior

Unresolved denials above policy threshold block dry-run-only continuation. The
operator must sustain denial history, request proof repair, or renew an operator
grant rather than continuing.

Stale review packets block by default. Policy may downgrade stale review to a
warning for metadata review trends, in which case the result status becomes
`capture_review_decision_ledger_ready_with_warnings`; no live capability is
created.

## Future sequence

1. Capture review decision ledger.
2. Operator review of decision trends.
3. Proof repair or grant renewal.
4. Rerun capture review packet.
5. Dry-run-only continuation.
6. Future live-candidate review only after explicit separate confirmation.
