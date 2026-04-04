# constitutional execution fabric (scoped slice)

This pass introduces a **typed constitutional mutation substrate** for a body-scale slice of mutation-capable actions.

## Covered in this slice

Canonical routed actions:

- `sentientos.manifest.generate` (`immutable_manifest_identity_writes`)
- `sentientos.quarantine.clear` (`quarantine_clear_privileged_operator_action`)
- `sentientos.genesis.lineage_integrate` (`genesisforge_lineage_proposal_adoption`)
- `sentientos.genesis.proposal_adopt` (`genesisforge_lineage_proposal_adoption`)
- `sentientos.codexhealer.repair` (`codexhealer_repair_regenesis_linkage`)
- `sentientos.merge_train.hold` / `sentientos.merge_train.release` (`merge_train_protected_mutation_hold_release`)

The machine-readable registry for this slice is at:
`glow/contracts/constitutional_execution_fabric_scoped_slice.json`.

## Not covered yet

- General task execution
- Full Cathedral action surfaces
- Full federation action set
- Repo-wide mutation universalization

## Action typing

Each routed mutation action carries:

- stable `action_id`
- mutation `domain`
- `authority_class`
- expected `lifecycle_phase`
- `correlation_id`
- declared provenance intent
- execution owner/source
- optional advisory context and typed payload

## Execution routing

`sentientos.constitutional_mutation_fabric.ConstitutionalMutationRouter` is the canonical execution substrate for this slice.

Flow:

1. validate action against registry metadata (fail closed if missing/mismatched)
2. delegate admission to existing control-plane kernel
3. execute canonical registered handler only on `allow`
4. emit normalized provenance linkage and router execution event

## Relationship to existing proof stack

- **Kernel admission:** unchanged authority and governor delegation semantics
- **Protected corridor proof:** preserved above execution; kernel decisions and protected intent still emitted
- **Bounded jurisprudence:** authority-of-judgment surfaces remain attached by existing control-plane decision machinery

## In-scope non-canonical paths still present

Within this scoped slice, canonical entry points now route through the constitutional mutation router.
Any remaining direct internal helper calls should be treated as implementation detail, not public canonical mutation interfaces.
