from __future__ import annotations

CANONICAL_MUTATION_DOMINANCE_NOTE = """
Scoped canonical mutation dominance (constitutional execution fabric slice)

Canonical mutation paths in-scope:
- sentientos.manifest.generate: scripts.generate_immutable_manifest.execute_manifest_generation_action -> constitutional router -> generate_manifest write.
- sentientos.quarantine.clear: scripts.quarantine_clear.main -> constitutional router -> integrity_quarantine.clear.
- sentientos.genesis.lineage_integrate + sentientos.genesis.proposal_adopt: GenesisForge.expand -> constitutional router -> SpecBinder.integrate / AdoptionRite.promote.
- sentientos.codexhealer.repair: CodexHealer.auto_repair -> constitutional router -> RepairSynthesizer.apply.
- sentientos.merge_train.hold/release: ForgeMergeTrain.hold/release -> constitutional router -> guarded transition helpers.

Non-canonical implementation details remaining:
- merge-train transition helper bodies remain internal implementation details and now reject direct non-canonical invocation.
- low-level mutation helper functions still exist for composition, but scoped public call surfaces route through typed actions.

Known residual scoped risk:
- in-process direct calls to low-level internals are still physically possible for privileged code authors; detection is scoped via sentientos.scoped_mutation_canonicality.evaluate_scoped_slice_non_canonical_paths.

Extension guidance:
- add new scoped actions by extending the scoped registry, binding exactly one canonical handler, and preserving typed-action -> router -> handler provenance markers.
- avoid adding parallel public mutators that bypass typed action registration.

Scoped slice-health temporal coherence (diagnostic-only):
- the scoped lifecycle health view writes a bounded derived history at glow/contracts/constitutional_execution_fabric_scoped_slice_health_history.jsonl.
- transition classes are intentionally narrow: initial_observation, unchanged, improving, degrading, recovered_from_failure, recovered_from_fragmentation.
- history rows remain non-sovereign and non-authoritative: they summarize observed lifecycle outcomes for legibility only.
- this history does not widen slice scope, does not add action families, does not decide admissions, and does not override kernel/corridor/jurisprudence protections.

""".strip()
