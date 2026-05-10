# Phase 97 External Security Review Packet — Execution Plan

## Goal

Phase 97 adds a deterministic `ExternalSecurityReviewPacket` contract that packages Phase 91 through Phase 96 provider-invocation denial evidence for security reviewer and auditor consumption. The packet is metadata-only: it links IDs, statuses, digests, high-level finding/constraint/gap codes, redaction counts, and proof markers without disclosing prompt material or runtime/provider material.

## Non-goals

Phase 97 does **not** authorize provider invocation, external execution, model calls, provider send, network egress, DNS resolution, socket or HTTP use, credential use, endpoint use, client/session/transport construction, provider SDK use, semantic generation, tool/action execution, memory retrieval, memory writes, retention, routing, admission, execution, or orchestration. It does not change `assemble_prompt(...)` behavior and does not modify `prompt_assembler.py`.

## Dependency chain: Phase 61 through Phase 96

Phase 97 depends on the prior context-hygiene spine: Phase 61 context packets; Phase 62 truth-gated selection; Phase 62B blocked-risk preservation; Phase 63 embodiment/privacy eligibility; Phase 64 prompt preflight; Phase 65 packet-local safety metadata; Phase 66 source-kind contracts; Phase 67 handoff manifests; Phase 68 dry-run envelopes; Phase 69 constraints; Phase 70 adapter contracts; Phase 71 compliance harness; Phase 72 shadow preview; Phase 73 shadow blueprint; Phase 74 audit receipts; Phase 75 guardrails; Phase 76 adversarial tests; Phase 77 policy decisions; Phase 78 operator review; Phase 79 synthetic-only candidates; Phase 80 internal no-LLM candidates; Phase 81 display/egress boundary; Phase 82 model-call preflight; Phase 83 model-call review; Phase 84 provider dry-run envelope; Phase 85 dry-run egress review; Phase 86 fixed-stub simulation; Phase 87 simulation/network preflight; Phase 88 network-egress review; Phase 89 null transport; Phase 90 null-only registry; Phase 91 transport capability custody; Phase 92 credential custody; Phase 93 endpoint custody; Phase 94 client custody; Phase 95 invocation readiness; and Phase 96 invocation denial review.

## External security review packet is not invocation

The packet is an audit/review metadata artifact only. A ready packet means the denial evidence is reviewable; it never means a provider call is approved. Accepted packets keep `invocation_allowed`, `provider_send_allowed`, `network_allowed`, credential/client/endpoint/provider SDK/tool/memory/action/retention/routing allowance flags false.

## Metadata-only packet contents

Allowed packet content is limited to stable metadata: packet ID, status, review scope, reviewer packet reference, linked Phase 91-96 IDs/digests/statuses, digest-only evidence links, audit-chain completeness, high-level summaries, redaction counts, constraints, warnings, compact rationale, and explicit no-runtime/no-sensitive-material proof markers.

## Evidence-link behavior

Evidence links contain only `artifact_kind`, `artifact_id`, `artifact_status`, `artifact_digest`, `included`, `redacted`, and `reason_code`. Artifact bodies, raw payloads, prompt text, secrets, endpoints, client/session/transport handles, provider SDK objects, network handles, runtime handles, model/provider parameters, tool schemas, and hidden chain-of-thought are excluded.

## Redaction and fail-closed behavior

The builder conservatively scans reviewer-supplied references and receipt rationale for prompt, secret, endpoint, client/session/transport, network, runtime, provider-parameter, tool-schema, hidden chain-of-thought, and invocation markers. Detected sensitive markers produce safe redaction counts and stable finding codes; packet readiness fails closed rather than exposing the sensitive value.

## Forbidden invocation invariant

Phase 97 blocks if Phase 96 denial review is missing, rejected, expired, invalid, not affirmed, or attempts a forbidden invocation override. It also blocks if the review scope is forbidden, any allowance flag is true, digest-chain evidence is incomplete when required, or sensitive/runtime/provider material is detected. Phase 96 remains a metadata gate only and is not invocation approval.

## Digest behavior

The packet digest is deterministic over stable metadata-safe fields. It changes when linked denial/readiness/evidence digests change, evidence links change, finding/constraint/gap summaries change, redaction summaries change, scope changes, reviewer packet reference changes, allowance flags change, or metadata-only/no-sensitive flags change. The digest excludes prompt text, raw payloads, credentials, endpoints, provider handles, network/runtime handles, LLM/provider parameters, hidden chain-of-thought, and nondeterministic timestamps.

## Guardrail behavior

`verify_context_hygiene_prompt_boundaries.py` scans the Phase 97 module by default. The module remains free of provider SDK imports, network/socket/HTTP/DNS/env/file/config/vault/keychain access, prompt assembler imports/calls, memory/action/retention/routing/orchestration calls, client/session/transport constructors, and model/provider APIs.

## Tests

`tests/test_phase97_external_security_review_packet.py` covers clean construction, allowed and forbidden scopes, missing/rejected/expired/invalid/override denial reviews, allowance-flag denial, sensitive marker fail-closed behavior, digest-only evidence links, no-sensitive-material predicates, deterministic digest changes, input immutability, static no-call checks, Phase 90-96 posture preservation, embodiment/blocked-candidate non-invocation, and guardrail inclusion.

## Deferred work

Future phases may add an external audit export receipt or formal provider-invocation denial attestation packet. Those future phases must preserve the same non-invocation posture unless an explicitly separate, reviewed, and approved architecture changes the provider boundary.
