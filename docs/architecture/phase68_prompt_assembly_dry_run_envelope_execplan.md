# Phase 68: Prompt Assembly Dry-Run Envelope (Execution Plan)

## Goal
Define a pure, non-authoritative dry-run envelope sourced exclusively from the Phase 67 context prompt handoff manifest. The envelope previews prompt-assembly readiness without assembling prompt text, retrieving memory, calling an LLM, writing memory, admitting work, routing work, executing work, triggering feedback, or committing retention.

## Source artifact
Phase 68 consumes the existing Phase 67 `ContextPromptHandoffManifest` as its only source. It copies only manifest-safe identifiers, digest, packet scope, section summaries, admissible reference summaries, caveats, block reasons, source-kind counts, safety-contract gaps, provenance posture, and rationale.

## Status mapping
- `handoff_ready` → `dry_run_ready`
- `handoff_ready_with_caveats` → `dry_run_ready_with_caveats`
- `handoff_blocked` → `dry_run_blocked`
- `handoff_not_applicable` → `dry_run_not_applicable`
- `handoff_invalid_packet` → `dry_run_invalid_manifest`

Unknown handoff status values fail closed as `dry_run_invalid_manifest`.

## Admissible reference rules
Admissible reference summaries are included only when the dry-run status is `dry_run_ready` or `dry_run_ready_with_caveats`. Blocked, not-applicable, and invalid manifests preserve block/caveat/provenance/safety summaries but withhold all admissible references.

## Assembly constraints
The envelope records constraints rather than prompt content:
- source artifact is the Phase 67 handoff manifest;
- the manifest id and digest remain visible;
- output is pure, non-authoritative, non-executing, and manifest-only;
- prompt assembly and final prompt text are explicitly absent;
- admissible refs are available only for ready or caveated manifests.

## No-runtime markers
The envelope contains explicit no-runtime marker booleans:
- `does_not_assemble_prompt`
- `does_not_contain_final_prompt_text`
- `does_not_call_llm`
- `does_not_retrieve_memory`
- `does_not_write_memory`
- `does_not_trigger_feedback`
- `does_not_commit_retention`
- `does_not_execute_or_route_work`
- `does_not_admit_work`

## Digest rules
The envelope digest is a deterministic SHA256 over stable envelope-safe fields with the digest field omitted. Changes in source manifest digest, status, caveats, block reasons, summaries, provenance, safety gaps, or admissible refs change the digest.

## Non-goals
- No prompt text generation or assembly.
- No prompt assembler integration.
- No memory manager, truth runtime, embodiment runtime, action, retention, routing, admission, execution, or orchestration behavior changes.
- No authoritative decision surface.

## Tests
See `tests/test_phase68_prompt_assembly_dry_run_envelope.py`.
