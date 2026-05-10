# Phase 98 External Audit Export Receipt Execplan

## Goal

Phase 98 adds a deterministic, metadata-only `ExternalAuditExportReceipt` for Phase 97 `ExternalSecurityReviewPacket` objects. The receipt records that a clean packet is eligible for external or internal audit export review without performing export I/O, external delivery, upload, e-mail, webhook, file write, object storage write, network egress, model invocation, tool execution, routing, retention, or memory access.

## Non-goals

- No provider invocation or provider SDK import.
- No prompt assembly and no change to live `assemble_prompt(...)` behavior.
- No packet body, artifact body, prompt text, raw payload, hidden chain-of-thought, secret, endpoint, client, session, transport, provider parameter, tool schema, or runtime handle exposure.
- No destination URL, e-mail address, webhook URL, storage bucket/object path, upload target, file path, credential, or executable call surface.

## Dependency chain

Phase 98 depends on the context-hygiene spine established by Phases 61 through 97: ContextPacket contracts, truth/risk gates, embodiment/privacy eligibility, prompt preflight and dry-run envelopes, prompt-boundary guardrails, policy/operator/internal display and model-call preflights, provider dry-run/simulation/null transport custody, credential/endpoint/client custody, invocation readiness and denial review, and the Phase 97 metadata-only external security review packet.

## Audit export receipt is not export I/O

The receipt is an audit record only. It may state that metadata-only export review is ready, ready with conditions, rejected, expired, invalid, missing a packet, blocked by packet readiness, blocked by sensitive material, blocked by runtime authority, blocked by invocation override, or blocked by I/O attempt. It never performs delivery or creates an egress path.

## Allowed and forbidden scopes

Allowed metadata-only scopes are:

- `external_audit_metadata_export_receipt`
- `internal_audit_metadata_export_receipt`
- `security_review_export_receipt`
- `invocation_denial_audit_export_receipt`

Forbidden scopes always block readiness:

- `live_external_delivery_forbidden`
- `provider_submission_forbidden`
- `network_upload_forbidden`
- `email_delivery_forbidden`
- `webhook_delivery_forbidden`
- `file_write_forbidden`
- `object_storage_forbidden`
- `tool_or_action_forbidden`

## Evidence summary behavior

Evidence is summarized by counts only: evidence links, included links, redacted links, finding summaries, constraint summaries, gap summaries, digest-chain completeness, and packet readiness. The receipt does not copy evidence bodies or artifact bodies.

## Redaction summary behavior

Redaction information remains counters and booleans only for prompt text, raw payloads, secrets, endpoints, clients, network handles, runtime handles, provider params, tool schemas, and hidden chain-of-thought. Rejected required redaction codes fail closed and prevent readiness.

## Sensitive material fail-closed rules

The receipt blocks when the Phase 97 packet or receipt metadata indicates prompt text, hidden chain-of-thought, raw payloads, secrets, secret references, endpoints, endpoint references, clients, client references, network handles, runtime handles, provider params, tool schemas, destination markers, provider invocation markers, or executable authority.

## No-export/no-invocation invariant

Ready receipts require all export I/O flags to remain false, all external delivery flags to remain false, all sensitive inclusion flags to remain false, all provider/network/runtime allowance flags to remain false, invocation denial to remain preserved, and provider invocation to remain forbidden. Approval is approval for metadata export review only, not provider invocation.

## Digest behavior

The export receipt digest is deterministic over stable metadata-safe fields. It changes when packet digest, expected packet digest, exporter reference, export label, scope, decision, accepted/rejected code lists, evidence summary, redaction summary, expiration, findings, warnings, constraints, I/O flags, allowance flags, or metadata/no-sensitive markers change. It does not include packet bodies, artifact bodies, prompt text, raw payloads, credentials, endpoints, provider handles, network handles, runtime handles, provider params, or hidden chain-of-thought.

## Guardrail behavior

The Phase 75 prompt-boundary scanner includes the Phase 98 module. The module is guarded against provider/network/socket/HTTP/DNS/config/secret/client/session/transport/export/upload/e-mail/webhook/storage/prompt/runtime imports or calls, while allowing metadata-only schema labels such as `external_audit_export_receipt_only`, `export_io_not_performed`, `external_delivery_not_performed`, `no_prompt_text`, `no_hidden_chain_of_thought`, and `provider_invocation_forbidden`.

## Tests

`tests/test_phase98_external_audit_export_receipt.py` covers clean receipts, allowed and forbidden scopes, decisions, expiration, packet digest matching, missing/not-ready Phase 97 packets, sensitive/runtime/invocation override detection, I/O flags, destination/provider/prompt/secret/endpoint/client/runtime adversarial markers, evidence/redaction summaries, helper predicates, digest stability and change sensitivity, mutation safety, static runtime-call absence, prior phase invariants, and guardrail scanning.

## Deferred work

Future work may define a formal denial-attestation packet or a separate external audit handoff interface. Those future phases must remain separate from this receipt and must introduce their own explicit review before any real export interface exists.
