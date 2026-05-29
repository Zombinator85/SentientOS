# Household presence camera future live-candidate deferral registry

The future live-candidate deferral registry is a deterministic, metadata-only registry for household presence camera review evidence. It records that future-live camera review or live-candidate consideration remains explicitly deferred and operator-only after dry-run-only continuation review.

It exists to prevent upstream dry-run readiness, trend history, renewal requests, decision history, or continuation gate outcomes from being interpreted as live capture readiness, operator consent, grant renewal, hardware access, media storage, speaker output, or external disclosure.

## Non-authority boundaries

The registry is not live hardware access. It never opens cameras, queries live devices, processes media, stores raw media, or calls capture stacks. It accepts only explicit local JSON metadata.

The registry does not schedule live review. Successful records set `deferral_schedules_live_review: false` and include `schedule_live_capture_review` in `forbidden_next_steps`.

The registry does not approve a live candidate. Successful records set `deferral_approves_live_candidate: false` and include `approve_live_candidate` in `forbidden_next_steps`.

The registry is not operator consent. It sets `deferral_grants_operator_consent: false`, forbids `infer_operator_consent_from_deferral`, and blocks upstream evidence that claims consent or live capture permission.

The registry is not grant renewal. It sets `deferral_renews_operator_grant: false`, forbids `convert_renewal_request_to_grant`, and treats renewal-request evidence as request history only.

The registry is not live readiness. It sets `deferral_confers_live_readiness: false`, forbids `convert_deferral_to_live_readiness`, and records dry-run continuation as `dry_run_continuation_not_live_readiness` when cited.

## Relationship to upstream layers

1. The capture review packet remains the review evidence packet; this registry only cites its digest and identifiers.
2. The capture review decision ledger remains decision history; this registry only records `decision_history_not_live_consent` when that history is relevant.
3. The operator review trend ledger remains trend history; this registry only records `trend_history_not_live_consent` when trends are cited.
4. The operator grant renewal request packet remains a request packet; this registry only records `grant_renewal_request_not_live_consent` and never renews a grant.
5. The dry-run-only continuation gate remains dry-run-only; this registry cites it as gate evidence and blocks if it is not ready or implies live authority.
6. The capture authorization envelope, capture denial ledger, policy chain, zone config, and disabled capture adapter contract remain separate boundaries whose digests can be referenced but not bypassed.

## Registry statuses

The registry emits ready statuses only when metadata evidence can safely record deferral:

- `future_live_deferral_registry_ready`
- `future_live_deferral_registry_ready_with_warnings`

It blocks missing evidence, stale evidence in block mode, scope mismatch, unsafe live implications, media payloads, speaker/talkback boundaries, external disclosure requests, unresolved denials, operator-grant-required contexts when policy disallows diagnostics, and proof-refresh-required contexts when policy disallows diagnostics.

## Deferral types

Supported deferral types include `future_live_review_deferred`, `live_candidate_review_not_requested`, `live_candidate_review_requires_separate_operator_confirmation`, `dry_run_continuation_not_live_readiness`, `grant_renewal_request_not_live_consent`, `trend_history_not_live_consent`, `decision_history_not_live_consent`, `unresolved_denial_blocks_future_live`, `proof_refresh_required_before_future_live_review`, `operator_grant_required_before_future_live_review`, `stale_evidence_requires_review_before_future_live`, `mixed_scope_requires_operator_review`, and `no_future_live_path_available`.

## Safe next actions

Safe next actions are metadata-only and include maintaining deferral, requiring operator review, requesting proof refresh, inspecting upstream ledgers, rerunning a capture review packet, or sustaining capture denial. None of these actions perform capture, grant authority, schedule live review, approve live candidates, produce speaker output, or disclose externally.

## Forbidden next steps

Every successful record includes forbidden next steps such as `open_camera_now`, `attempt_capture`, `enable_live_capture`, `enable_live_recording`, `store_raw_media`, `attach_media_payload`, `schedule_live_capture_review`, `approve_live_candidate`, `mark_live_ready`, all upstream-bypass actions, consent inference from gate/trend/request/deferral history, conversion of request or deferral evidence into grants or live readiness, `enable_speaker_output`, and `enable_external_disclosure`.

## Stale, scope, and denial behavior

Stale gate, request, trend, and review evidence can warn or block depending on policy. Warnings never merge scope into authority and never imply live readiness.

Scope mismatch blocks by default. Mixed-scope diagnostic summaries are allowed only when policy explicitly enables them; the resulting output is `ready_with_warnings` and remains operator-review-only.

Unresolved denials above policy threshold block future-live deferral because there is no safe future-live path while denial history remains unresolved.

## No media, no hardware, no live runtime

Fixtures and CLI inputs are metadata-only. They must not contain images, audio, video, thumbnails, screenshots, base64 media, raw transcripts, or real hardware serials. The library never invokes live camera modules, hardware APIs, providers, network APIs, shell delegation, speaker runtime behavior, or external authority behavior.

## Future sequence

1. Capture review decision ledger.
2. Operator review trend ledger.
3. Operator grant renewal request packet.
4. Dry-run-only continuation gate.
5. Future live-candidate deferral registry.
6. Explicit proof repair or operator grant renewal outside this registry.
7. Rerun capture review packet.
8. Future live-candidate review only after explicit separate confirmation in a later task.
