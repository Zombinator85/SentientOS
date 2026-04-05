# Scoped canonical trace coherence

This note defines trace coherence for the current constitutional mutation slice only:

- `sentientos.manifest.generate`
- `sentientos.quarantine.clear`
- `sentientos.genesis.lineage_integrate`
- `sentientos.genesis.proposal_adopt`
- `sentientos.codexhealer.repair`
- `sentientos.merge_train.hold`
- `sentientos.merge_train.release`

## What trace coherence means in this slice

A scoped mutation is **trace coherent** when one stable `correlation_id` can be followed through:

1. typed action identity (`TypedMutationAction.action_id`)
2. router execution event (`constitutional_mutation_router_execution`)
3. kernel admission decision (`kernel_decision:<correlation_id>`)
4. canonical handler identity
5. side-effect artifact/event
6. proof-facing surface that carries the canonical admission reference

## Expected link fields

- `correlation_id`
- `admission_decision_ref`
- `typed_action_id`
- `canonical_router`
- `canonical_handler`
- `path_status=canonical_router`

For this pass, merge-train hold/release include canonical admission linkage in
`pulse/forge_train_events.jsonl` (`train_held`/`train_released`) so side effects and proof events can be joined directly.

Genesis update in this pass:

- `sentientos.genesis.proposal_adopt` closes as trace-complete when:

- live mount artifact admission (`live/*.json:admission`) carries `correlation_id`, `typed_action_id=sentientos.genesis.proposal_adopt`, `admission_decision_ref`
- codex index admission (`codex.json[].admission`) carries the same tuple
- codex index also records lineage join fields:
  - `lineage_typed_action_id=sentientos.genesis.lineage_integrate`
  - `lineage_correlation_id`
  - `lineage_admission_decision_ref`

- `sentientos.genesis.lineage_integrate` closes as trace-complete when:
  - lineage artifact (`lineage/lineage.jsonl`) carries `correlation_id`, `typed_action_id=sentientos.genesis.lineage_integrate`, `admission_decision_ref`
  - lineage row carries `daemon_spec_path`
  - `daemon_spec_path` resolves to the written daemon spec artifact

This removes inference through disconnected proposal/spec joins by making lineage→spec and lineage→adoption canonical linkage explicit in proof-visible fields.

Healer update in this pass:

- `sentientos.codexhealer.repair` closes as trace-complete when the recovery ledger row (`integration/healer_runtime.log.jsonl`) contains:
  - `canonical_admission.typed_action_id=sentientos.codexhealer.repair`
  - `canonical_admission.admission_decision_ref=kernel_decision:<correlation_id>`
  - `canonical_admission.canonical_handler`
  - `canonical_admission.path_status=canonical_router`
  - plus `details.kernel_admission` carrying the same typed action and admission decision reference.

This removes inference where healer history previously depended on reading only nested `details.kernel_admission` fields without a stable proof-visible canonical tuple on the recovery ledger row itself.

## Remaining scoped fragmentation

- Denied-path semantics are now scoped explicitly:
  - `trace_denied_canonical`: canonical router+kernel denial linkage is present, no success side-effect leak, and denial evidence is machine-readable (healer/quarantine include explicit denial records).
  - `trace_denied_fragmented`: denial happened but canonical denial evidence is incomplete (missing denial record, missing linkage, or mismatched denial metadata).
  - `trace_denied_erroneous`: denial happened but success-path side effects still appeared for the same correlation/action.
- Clean canonical denial semantics in this slice are now enforced for:
  - `sentientos.codexhealer.repair` (denied governor path must emit ledger denial with canonical admission linkage).
  - `sentientos.quarantine.clear` (denied event uses the kernel disposition instead of hardcoded deny).
- Still unresolved/fragile:
  - non-healer denied paths remain mostly router/kernel-event scoped; they are legible but not yet backed by richer denial-specific artifact proof layers.
- The scoped evaluator intentionally does not universalize to unrelated action families.

Canonical success history (`trace_complete`) and canonical denied history (`trace_denied_canonical`) are intentionally distinct classes: success requires side-effect completion linkage, while denied requires explicit non-execution plus honest denial evidence and no success leakage.

## Admitted-after-admission failure semantics (this pass)

The scoped evaluator now treats post-admission execution failure as a first-class trace state separate from success and denial:

- `trace_failed_canonical`: admitted (`final_disposition=allow`), handler started and failed, canonical failure payload present (`failure.exception_type`), and explicit partial-side-effect state present (`partial_side_effect_state=unknown_partial_side_effects_possible`).
- `trace_failed_fragmented`: admitted failure is indicated but canonical failure linkage is incomplete (for example missing `failure` payload or missing partial-side-effect state).
- `trace_failed_erroneous`: admitted failure is recorded, but success-side effects still appear for the same correlation in scoped proof surfaces.

### Compact admitted-failure map for the current scoped slice

- `sentientos.manifest.generate`: **clean** — canonical router now emits machine-readable failure metadata on admitted handler exceptions.
- `sentientos.quarantine.clear`: **fragile** — router-level admitted failures are now legible, but domain-specific failed-clear artifact semantics are still sparse.
- `sentientos.genesis.lineage_integrate`: **fragile** — router-level failure legibility is present; lineage/artifact partial-write reconciliation remains domain-local.
- `sentientos.genesis.proposal_adopt`: **fragile** — router-level failure legibility is present; live/codex partial-write interpretation remains action-specific.
- `sentientos.codexhealer.repair`: **clean** — denial and success already had canonical linkage; admitted handler exceptions now preserve canonical failure evidence.
- `sentientos.merge_train.hold`: **fragile** — admitted failure is now visible at router level, but side-effect split (state write vs event emit) can still produce partial artifacts.
- `sentientos.merge_train.release`: **fragile** — same as hold.

Incomplete side effects and clean failure are intentionally distinct: clean admitted failure now means explicit canonical failure evidence with typed action + admission linkage, while side-effect completeness remains independently classified and must not be inferred as success.

## How to extend without re-fragmenting

When extending this scoped slice, require each new side-effect artifact/event to record the same stable linkage tuple (`correlation_id`, `admission_decision_ref`, `typed_action_id`) emitted by the canonical router path. Keep the check narrow and action-explicit instead of introducing global trace taxonomies.
