# Phase 77 Context Hygiene Policy Decision Layer Exec Plan

## Goal

Phase 77 adds a deterministic prompt-materialization policy decision point for the Phase 61-76 context-hygiene runway. It consumes Phase 74 audit receipt metadata, Phase 73 blueprint status, shadow preview/compliance/adapter status, digest-chain evidence, caveats, warnings, findings, source-kind summaries, and explicit feature-flag/operator-review state to produce a policy decision artifact.

The policy decision can report one of four practical postures for Phase 77: deny, shadow-only, operator-review-required, or synthetic-fixture-only allowed. It is deny-by-default.

## Non-goals

Phase 77 does not enforce policy, materialize prompts, assemble prompts, call LLMs, retrieve memory, write memory, trigger feedback, commit retention, execute actions, route work, admit work, or modify runtime behavior. It is a PDP-style contract and precondition artifact only.

## Phase 61 through Phase 76 dependency chain

1. Phase 61 created context packets and receipts.
2. Phase 62 added truth-gated context selection.
3. Phase 62B preserved blocked attempted-candidate contamination.
4. Phase 63 added embodiment/privacy eligibility adapters.
5. Phase 64 added prompt preflight.
6. Phase 65 preserved packet-local safety metadata.
7. Phase 66 added source-kind safety contracts.
8. Phase 67 added prompt handoff manifests.
9. Phase 68 added prompt assembly dry-run envelopes.
10. Phase 69 added prompt assembly constraint verification.
11. Phase 70 added prompt assembly adapter payload contracts.
12. Phase 71 added prompt assembler compliance checks.
13. Phase 72 added shadow adapter previews.
14. Phase 73 added shadow blueprint contracts.
15. Phase 74 added prompt materialization audit receipts.
16. Phase 75 added static CI prompt-boundary guardrails.
17. Phase 76 added adversarial/property-style failure-mode tests.
18. Phase 77 consumes safe metadata from this runway and emits policy decisions only.

## Policy decision is not enforcement or materialization

The Phase 77 module emits structured dataclasses and helpers. Its explicit non-runtime markers state that policy enforcement is not included and that the decision does not contain prompt text, assemble prompts, call LLMs, retrieve/write memory, trigger feedback, commit retention, execute/route work, or admit work.

## Policy input fields

`PromptMaterializationPolicyInput` accepts metadata-only fields, including receipt identity/status/digest, digest-chain completeness, audit shadow-materializer allowance, blueprint/preview/compliance/adapter status, packet identity/scope, source-kind summary, caveats, warnings, violations, findings, boundary/provenance/privacy/truth/safety summaries, reference/section counts, requested policy ring, synthetic-fixture-only state, operator-review state, feature flags, environment label, and non-runtime markers.

It must not carry prompt text, raw payloads, raw memory, raw screen/audio/vision/multimodal data, execution/action/retention/retrieval handles, or LLM parameters.

## Status and ring model

Statuses are compact strings:

- `policy_deny`
- `policy_shadow_only`
- `policy_operator_review_required`
- `policy_synthetic_materialization_allowed`
- `policy_invalid_input`
- `policy_runtime_wiring_detected`

Rings are data-only strings:

- `ring_shadow_metadata_only`
- `ring_shadow_receipt_only`
- `ring_operator_review_queue`
- `ring_synthetic_fixture_only`
- `ring_internal_candidate_no_llm`
- `ring_live_llm_forbidden`

Phase 77 forbids internal/live/LLM-capable rings as allowance targets.

## Deny-by-default rules

The policy denies malformed or missing audit inputs, blocked/not-applicable/invalid/runtime-wiring audit status, incomplete digest chains, audit receipts that do not allow shadow materializer, prompt/raw/runtime authority markers, blocking violations/findings, blocked/not-applicable/invalid chain statuses, live/internal/LLM-capable rings, missing/disabled feature flags, missing required operator review, synthetic requests without `synthetic_fixture_only=True`, and unknown source kinds or rings.

## Shadow-only and synthetic-fixture allowance rules

Shadow-only can be returned when a ready audit receipt allows shadow materializer, the digest chain is complete, there are no blocking findings/violations, the requested ring is a shadow ring, the shadow feature flag is explicitly enabled, and no operator review is required.

Synthetic-fixture allowance can be returned only for `ring_synthetic_fixture_only` with `synthetic_fixture_only=True`, explicit synthetic feature flag enablement, accepted review for review-required warnings/caveats, complete ready/ready-with-warnings audit evidence, no blocking findings/violations, no prompt/raw/runtime authority markers, and no live/LLM/action/retention/memory capability.

## Operator-review-required behavior

If audit evidence is otherwise ready and warnings/caveats require review, a request for the operator review queue or higher returns `policy_operator_review_required` when review is missing. Accepted review may allow a synthetic-fixture-only decision if every other synthetic-fixture gate passes.

## Digest behavior

`compute_prompt_materialization_policy_digest(...)` hashes stable policy-safe decision fields. The digest changes when status, requested/effective ring, receipt digest, reasons/mitigations, warning/violation/finding counts, feature flag state, operator review state, or synthetic-fixture-only posture changes. It excludes raw payloads, prompt text, runtime handles, LLM parameters, and nondeterministic timestamps.

## Tests

Phase 77 tests cover malformed/missing inputs, blocked/not-applicable/invalid/runtime-wiring receipts, missing audit shadow allowance, shadow-only allowance, operator review, feature flags, forbidden rings, synthetic-fixture gates, prompt/raw/runtime markers, violations/findings, unknown source kinds/rings, non-runtime markers, deterministic digests, helper determinism, mutation safety, no assemble/runtime calls, Phase 63-to-77 happy path, Phase 62B blocked candidate denial, Phase 75 guardrail inclusion, and import purity.

## Deferred work

Future phases may add enforcement, materializer implementations, operator-review queue persistence, or synthetic materializer execution. Those are explicitly outside Phase 77 and must preserve the no-live-LLM/no-runtime authority boundary until separately designed and reviewed.
