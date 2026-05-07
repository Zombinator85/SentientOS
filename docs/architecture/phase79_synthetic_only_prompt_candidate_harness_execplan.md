# Phase 79 Synthetic-Only Prompt Candidate Harness Execplan

## Goal

Phase 79 adds a deterministic, pure-Python harness that can render prompt-shaped candidate text from explicitly synthetic fixtures only. The harness exists to test formatting, caveat visibility, and boundary preservation before any real context prompt-candidate path exists.

## Non-goals

- No live prompt materialization.
- No real context materialization.
- No `prompt_assembler.py` integration.
- No LLM or provider call path.
- No memory retrieval or memory write.
- No retention, action, routing, admission, execution, orchestration, or feedback behavior.
- No raw payload rendering.
- No system/developer authority creation from fixture refs.

## Dependency chain

Phase 79 depends on the context-hygiene spine established by:

1. Phase 61 `ContextPacket` schemas and receipts.
2. Phase 62 truth-gated context selection.
3. Phase 62B blocked-risk and attempted-candidate contamination preservation.
4. Phase 63 embodiment/privacy eligibility adapters.
5. Phase 64 prompt preflight.
6. Phase 65 packet-local safety metadata preservation.
7. Phase 66 source-kind safety contracts.
8. Phase 67 prompt handoff manifest.
9. Phase 68 prompt assembly dry-run envelope.
10. Phase 69 prompt assembly constraint verifier.
11. Phase 70 prompt assembly adapter contract.
12. Phase 71 prompt assembler compliance harness.
13. Phase 72 shadow adapter preview hook.
14. Phase 73 shadow blueprint contract.
15. Phase 74 prompt materialization audit receipt and attestation.
16. Phase 75 static prompt-boundary guardrails.
17. Phase 76 adversarial/property-style failure-mode tests.
18. Phase 77 pure policy decision layer.
19. Phase 78 operator review receipt contracts.

## Synthetic-only materialization is not live materialization

The Phase 79 harness may produce prompt-shaped text only for synthetic fixtures. That text is explicitly marked `SYNTHETIC FIXTURE ONLY`, identifies itself as not real user/context/memory content, and has no runtime authority.

## Fixture-only input rules

Inputs must include:

- Phase 77 `policy_decision`.
- Phase 74 `audit_receipt`.
- Optional Phase 78 `operator_review_receipt`.
- `synthetic_fixture_only=True`.
- `requested_ring=ring_synthetic_fixture_only`.
- Synthetic `fixture_id` and `fixture_scope` using `synthetic:`, `fixture:`, or `test:` prefixes.
- Synthetic refs and sections using the same visible synthetic prefixes.
- Allowed boundary notes and expected caveats.
- Explicit feature flag state.

Real-looking packet IDs, memory refs, source paths, real paths, URIs, provenance refs, adapter payload IDs, raw payload fields, runtime handles, and LLM/tool/action/retention/memory capability markers block the candidate.

## Gating rules

The harness blocks unless:

- Phase 77 policy status allows the synthetic materializer.
- Phase 74 audit receipt allows the shadow materializer.
- Phase 78 review satisfies the policy decision when review is required.
- Every ref, section, fixture ID, and fixture scope is synthetic.
- No hard findings remain.
- Required caveats and boundary notes are preserved.
- The candidate remains no-LLM, no-tool, no-memory, no-retention, no-action, no-routing, no-admission, no-execution, and no-feedback.

## Prompt-shaped text rules

Rendered text:

- Labels itself `SYNTHETIC FIXTURE ONLY`.
- Says it is not real user/context/memory content.
- Uses fixture summaries only.
- Preserves caveats and boundary notes visibly.
- Labels refs as untrusted/reference-only.
- Does not produce system or developer instruction sections.
- Does not include raw payloads, runtime handles, LLM/tool parameters, or hidden chain-of-thought.

## Guardrail allowlist update

The Phase 75 boundary verifier now scans the synthetic materializer by default. It narrowly allowlists synthetic-specific names (`synthetic_prompt_text`, `synthetic_prompt_candidate`, `SyntheticPromptCandidate`) only in:

- `sentientos/context_hygiene/prompt_synthetic_materializer.py`
- `tests/test_phase79_synthetic_only_prompt_candidate_harness.py`

The guardrail still rejects `final_prompt_text`, `assembled_prompt`, `system_prompt`, `developer_prompt`, raw payload keys, runtime handles, forbidden imports, runtime calls, and any `assemble_prompt(...)` call.

## Tests

Phase 79 tests cover successful synthetic fixture rendering, warning rendering, policy denial, shadow-only denial, operator review required/accepted/rejected/expired/digest mismatch paths, audit gating, non-synthetic IDs, real memory/source/path/URI/provenance refs, raw payload markers, runtime/capability markers, prompt injection handling, caveat/boundary visibility, digest determinism and sensitivity, immutability, guardrail allowlisting, and import/runtime purity.

## Deferred work

- Any future internal no-LLM candidate path must remain separately gated and must not reuse Phase 79 as authority for real context.
- Live `assemble_prompt(...)` behavior remains untouched.
- Real context prompt candidate materialization remains forbidden until a later phase explicitly designs and audits it.
