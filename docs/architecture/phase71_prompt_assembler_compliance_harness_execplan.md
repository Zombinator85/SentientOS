# Phase 71 Prompt Assembler Compliance Harness Exec Plan

## Goal

Add a pure compliance harness that defines and tests the prompt-assembler-side rules a future context hygiene integration must satisfy before any prompt assembler wiring is introduced.

## Non-goals

- Do not modify `prompt_assembler.py`.
- Do not wire Phase 70 adapter payloads into `prompt_assembler.py`.
- Do not assemble prompts from context hygiene packets, manifests, envelopes, candidate plans, or adapter payloads.
- Do not call an LLM, web client, provider SDK, retrieval path, or memory path.
- Do not retrieve memory or write memory.
- Do not modify truth, embodiment, action, retention, routing, admission, execution, or orchestration runtime behavior.

## Dependency chain

- Phase 61 created `ContextPacket` schema and receipts.
- Phase 62 added truth-gated context selection.
- Phase 62B made `blocked` first-class and preserved attempted-candidate contamination.
- Phase 63 added embodiment/privacy context eligibility adapters.
- Phase 64 added prompt preflight.
- Phase 65 preserved packet-local safety metadata.
- Phase 66 added per-source-kind safety contract completeness.
- Phase 67 added a prompt handoff manifest.
- Phase 68 added a prompt assembly dry-run envelope.
- Phase 69 added a prompt assembly constraint verifier.
- Phase 70 added a prompt assembly adapter contract.
- Phase 71 adds a compliance harness for future prompt assembler integration requirements only.

## Compliance harness is not prompt assembly

The harness evaluates `PromptAssemblyAdapterPayload` contract readiness and statically scans `prompt_assembler.py` source text for context hygiene wiring or bypass patterns. It emits compliance reports and future integration rules. It does not produce prompt text, does not call a model, and does not grant runtime authority.

## Adapter compliance rules

Future prompt assembler consumption is allowed only when all blocking rules pass:

1. Adapter status is `adapter_ready` or `adapter_ready_with_warnings`.
2. `adapter_blocked`, `adapter_not_applicable`, `adapter_invalid_verification`, and `adapter_invalid_candidate_plan` block prompt materialization.
3. No final prompt text is present.
4. No raw payloads are present.
5. No runtime authority is present.
6. `non_authoritative` posture is preserved.
7. Caveat fields are preserved or reported as warnings when absent.
8. Provenance notes are preserved or reported as warnings when absent.
9. Privacy notes are preserved or reported as warnings when absent.
10. Truth notes are preserved or reported as warnings when absent.
11. Safety notes are preserved or reported as warnings when absent.
12. Adapter refs are present only when status allows consumption.
13. Adapter refs are absent when status blocks consumption.
14. No-runtime guards cover LLM calls, memory retrieval/write, execution/routing/admission, retention commit, and feedback triggers.
15. Digest is present.
16. Packet, envelope, and candidate identifiers are present.

## Static prompt assembler scan behavior

The scan is source-text/AST-only. It does not import or execute `prompt_assembler.py`. It reports whether the current prompt assembler source imports context hygiene adapter modules, imports `prompt_adapter_contract`, uses `ContextPacket`, calls selector/preflight/manifest/envelope/verifier/adapter helpers, bypasses the adapter contract by reading context hygiene internals, retrieves memory for context hygiene purposes, calls LLM/provider APIs for context hygiene purposes, or contains Phase 70 adapter payload usage.

Pre-integration absence of context hygiene wiring is expected and is not a failure. Forbidden context bypass or unexpected active wiring is reportable.

## Future integration contract

A future prompt assembler integration must:

- accept only `PromptAssemblyAdapterPayload`;
- reject adapter statuses other than `adapter_ready` and `adapter_ready_with_warnings`;
- consume only `adapter_refs`;
- preserve caveats/provenance/privacy/truth/safety notes;
- never include raw payloads;
- never treat adapter payload as authoritative;
- not retrieve bypass context;
- not bypass the Phase 69 verifier;
- not bypass the Phase 68 envelope;
- not bypass the Phase 64 preflight;
- not bypass the Phase 62 selector;
- not make blocked refs prompt-visible;
- emit or record a compliance outcome before materialization in a future phase.

## Tests

`tests/test_phase71_prompt_assembler_compliance_harness.py` covers ready, warned, blocked, not-applicable, invalid-verification, and invalid-candidate-plan adapter statuses; prompt text/raw payload/runtime authority failures; boundary-note warnings; adapter ref status alignment; digest and identity requirements; static prompt assembler scanning; non-runtime report markers; import purity; Phase 63-to-71 pass-through; and Phase 62B blocked candidate materialization blocking.

## Deferred work

- Actual `prompt_assembler.py` integration remains deferred.
- Prompt materialization from adapter refs remains deferred.
- Compliance outcome persistence, if desired, remains deferred to the future integration phase.
- LLM/provider execution remains outside this harness.
