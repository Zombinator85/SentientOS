# Household Presence Camera Operator Review Trend Ledger

The Household Presence Camera Operator Review Trend Ledger is a deterministic, metadata-only review layer for Household Presence camera governance. It summarizes the decision history emitted by the Household Presence camera capture review decision ledger so reviewers can see repeated denials, recurring repair requests, operator grant renewal pressure, dry-run-only continuation history, future-live-review deferral history, stale-review patterns, and mixed operator review patterns.

This ledger does not make capture decisions, does not authorize capture, and does not replace operator review. Trend history is evidence for inspection only.

## Non-authority boundary

The trend ledger never opens cameras, accesses microphones, calls live hardware APIs, processes image/video/audio, accepts base64 media payloads, stores media payloads, invokes provider/network/GitHub APIs, enables speaker output, or discloses information externally. It reads explicit local JSON metadata and emits deterministic JSON metadata.

Every successful trend record pins these boundaries:

- `capture_enabled: false`
- `capture_available: false`
- `live_hardware_enabled: false`
- `raw_media_storage_enabled: false`
- `no_live_capture_performed: true`
- `speaker_output_enabled: false`
- `external_disclosure_enabled: false`
- `trend_enables_live_capture: false`
- `trend_confers_operator_consent: false`

## Relationship to upstream camera ledgers

1. **Capture authorization envelope** records whether a candidate request has the required metadata prerequisites. The trend ledger cannot bypass that envelope.
2. **Capture denial ledger** records denied capture attempts and unresolved denial counts. The trend ledger can summarize denial history but cannot clear it.
3. **Capture review packet** aggregates prerequisite proofs for operator review. The trend ledger can recommend rerunning the packet when repeated rejection appears.
4. **Capture review decision ledger** records operator review decisions. The trend ledger consumes those records as source metadata and does not mutate them.
5. **Disabled capture adapter contract** remains the enforcement boundary for no-live-capture operation. The trend ledger cannot override it.

## Trend types

The ledger can emit these metadata-only trend types:

- `repeated_capture_denials`
- `repeated_review_deferrals`
- `repeated_operator_grant_renewals`
- `repeated_dry_run_repairs`
- `repeated_policy_chain_repairs`
- `repeated_zone_config_repairs`
- `repeated_disabled_capture_boundary_repairs`
- `dry_run_only_continuation_history`
- `future_live_review_deferred_history`
- `sustained_denial_history`
- `rejected_review_packet_history`
- `stale_review_pattern`
- `mixed_operator_review_pattern`
- `no_trend_detected`

Repeated decision trends use the policy `repeated_threshold` (default `2`). Stale review detection uses `stale_review_threshold` (default `1`) and `stale_review_mode` (`warn` by default, `block` when selected).

## Safe next actions

Trend records map to operator-only safe next actions:

- `sustain_capture_denial` for repeated or sustained denial history.
- `operator_review_required` for deferral and stale review patterns.
- `renew_operator_grant` for grant-renewal pressure.
- `repair_dry_run_proof`, `repair_policy_chain_proof`, `repair_zone_config`, or `repair_disabled_capture_boundary` for matching repair trends.
- `rerun_capture_review_packet` for rejected review packet history.
- `continue_dry_run_only_review` for dry-run-only continuation history.
- `defer_future_live_review` for future-live-review deferral history.
- `inspect_decision_history` for mixed or no-trend summaries.

Safe next actions are not authority. Dry-run continuation history is not live readiness, and trend history is not operator consent.

## Forbidden next steps

Every successful record explicitly forbids opening cameras, attempting capture, enabling live capture or recording, storing or attaching media payloads, bypassing prerequisite ledgers, inferring operator consent from trends, converting trends to live readiness, enabling speaker output, or enabling external disclosure.

## Scope mismatch behavior

By default, decision records must share a single scope key derived from candidate, requested mode, and operator label. Scope mismatch blocks with `operator_review_trend_ledger_blocked_scope_mismatch`. If `allow_mixed_scope_summary` is enabled, the ledger may emit `operator_review_trend_ledger_ready_with_warnings`, but this mixed-scope summary remains metadata-only and never merges scope into authority.

## Future sequence

The intended governance sequence is:

1. Capture review decision ledger.
2. Operator review trend ledger.
3. Proof repair or grant renewal trend review.
4. Rerun capture review packet.
5. Dry-run-only continuation review.
6. Future live-candidate review only after explicit separate confirmation.
