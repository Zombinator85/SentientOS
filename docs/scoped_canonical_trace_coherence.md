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

For this pass, merge-train hold/release now include canonical admission linkage in
`pulse/forge_train_events.jsonl` (`train_held`/`train_released`) so side effects and proof events can be joined directly.

## Remaining scoped fragmentation

- Genesis and codex-healer side-effect resolution is still partially fragmented in the scoped checker: router+kernel linkage is evaluated, but deep side-effect lookup remains explicitly marked as partial until those artifact resolvers are added.
- The scoped evaluator intentionally does not universalize to unrelated action families.

## How to extend without re-fragmenting

When extending this scoped slice, require each new side-effect artifact/event to record the same stable linkage tuple (`correlation_id`, `admission_decision_ref`, `typed_action_id`) emitted by the canonical router path. Keep the check narrow and action-explicit instead of introducing global trace taxonomies.
