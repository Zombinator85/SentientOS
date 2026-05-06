# Phase 76: Context Hygiene Adversarial Failure-Mode Harness Execplan

## Goal
Phase 76 adds a deterministic adversarial and property-style test harness for the Phase 61-75 context-hygiene prompt assembly runway. The harness proves that malicious or malformed metadata cannot smuggle prompt text, raw payloads, blocked refs, runtime authority, missing caveats, digest mismatches, or bypass paths through the shadow prompt assembly chain.

## Non-goals
- Do not materialize prompt text.
- Do not assemble final prompts.
- Do not call an LLM or provider SDK.
- Do not retrieve memory or write memory.
- Do not trigger feedback, commit retention, route work, admit work, execute work, or orchestrate runtime behavior.
- Do not modify truth, embodiment, action, retention, routing, admission, execution, orchestration, or live `assemble_prompt(...)` runtime behavior.

## Phase 61 through Phase 75 dependency chain
- Phase 61: `ContextPacket` schema and receipts.
- Phase 62: truth-gated context selection.
- Phase 62B: blocked risk and attempted-candidate contamination.
- Phase 63: embodiment/privacy context eligibility adapters.
- Phase 64: prompt preflight.
- Phase 65: packet-local safety metadata preservation.
- Phase 66: source-kind safety contracts.
- Phase 67: prompt handoff manifest.
- Phase 68: prompt assembly dry-run envelope.
- Phase 69: prompt assembly constraint verifier.
- Phase 70: prompt assembly adapter contract.
- Phase 71: prompt assembler compliance harness.
- Phase 72: prompt assembler shadow adapter preview hook.
- Phase 73: prompt assembler shadow blueprint contract.
- Phase 74: prompt materialization audit receipt / attestation.
- Phase 75: static CI prompt-boundary guardrails.

## Harness is not prompt materialization
The Phase 76 harness creates malicious metadata and malformed artifact fixtures only. It validates with existing pure gates, shadow previews, blueprints, audit receipts, and static guardrails. It never concatenates context into prompt prose, never asks for final prompt text, and never invokes `assemble_prompt(...)` except as a monkeypatched sentinel that fails if called.

## Adversarial fixture categories
- Prompt injection strings in content summaries, caveats, rationale, provenance notes, privacy notes, truth notes, and safety notes.
- Forbidden prompt-materialization fields such as `prompt_text`, `final_prompt_text`, `assembled_prompt`, `rendered_prompt`, `system_prompt`, and `developer_prompt`.
- Raw payload fields such as `raw_payload`, raw memory/screen/audio/vision/multimodal payloads, and legacy raw perception aliases.
- Capability smuggling fields for LLM/provider params and execution/action/retention/retrieval/browser/mouse/keyboard handles.
- Runtime-authority booleans for memory writes, feedback triggers, retention commits, routing, admission, execution, and fulfillment.
- Blocked, excluded, unknown, and unknown-source-kind refs.
- Digest and identity mismatches across envelope, adapter payload, blueprint, packet, envelope, and candidate-plan identities.
- Warning, caveat, violation, privacy, truth, and safety note downgrade/removal attempts.

## Pipeline block/withhold expectations
- Selector and packet validation exclude raw, blocked, and unknown-source-kind candidates while preserving blocked contamination in packet risk.
- Prompt preflight blocks ineligible packets and authority/privacy/action gaps.
- Handoff manifests and dry-run envelopes withhold admissible refs for blocked, not-applicable, and invalid states.
- The Phase 69 verifier fails non-admissible refs, missing caveats, boundary loss, raw/prompt/runtime fields, digest mismatch, and identity mismatch.
- The Phase 70 adapter withholds refs when verification is blocked/invalid/not-applicable.
- The Phase 71 compliance harness blocks prompt/raw/runtime authority gaps and records missing identifier/note warnings.
- The Phase 72 preview blocks materialization and exposes counts/status/metadata only.
- The Phase 73 blueprint emits no refs or sections when blocked.
- The Phase 74 audit receipt refuses shadow-materializer allowance for blocked, invalid-chain, raw, prompt-text, runtime-authority, stale, or mismatched evidence.
- The Phase 75 guardrail script detects forbidden prompt fields, runtime imports/calls, and bypass paths in temporary source fixtures.

## Deterministic property-style loop
The harness uses a compact fixed list of adversarial cases and runs the same builders twice. For each case it records verification status, verification violation codes, compliance status, and compliance gap codes, then asserts both runs are byte-stable in sorted tuple form.

## Runtime sentinel testing
The harness monkeypatches live prompt assembly, memory retrieval, action-feedback, affective capture, and feedback registration paths to fail if called. Shadow preview, shadow blueprint, verifier, adapter, and audit receipt builders must complete without touching those sentinels.

## Tests
- `tests/test_phase76_context_hygiene_adversarial_failure_modes.py` covers prompt injection metadata, prompt/raw/capability/runtime authority field smuggling, blocked/excluded/unknown refs, source-kind fail-closed behavior, digest/identity mismatch, caveat/warning/violation/note downgrades, static guardrail temporary fixtures, runtime sentinels, clean artifact no-field assertions, and deterministic property-style loops.

## Deferred work
- Any future synthetic materializer must be introduced only after Phase 76 remains green and must consume only audited, ready, non-authoritative metadata.
- Future phases should add materializer-specific negative tests before enabling any prompt-text generation path.
- No live `assemble_prompt(...)` behavior is changed by this phase.
