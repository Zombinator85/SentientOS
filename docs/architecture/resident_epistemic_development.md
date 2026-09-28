# Bounded resident epistemic development

`ResidentEpistemicDevelopmentRuntime` composes, but does not replace, persistent
epistemic custody. Its versioned operator configuration names an existing
proposition and digest, allowed namespace, bounded equality selectors over typed
World-State fields, an explicit evidence relation, dependency and reliability
postures, and a frozen qualitative rule revision.

For each maintenance tick, cognition first captures and consumes its prior-only
projection. Only after that slot closes may the runtime validate the same tick's
`WorldStateSnapshot`, construct an exact source proof and evidence binding,
request a narrow evidence-stage admission, and append the binding. It then
reconstructs complete bounded evidence membership, creates a deterministic-rule
candidate, requests a different state-stage admission, and attempts one CAS
advancement per proposition. The result is `next_tick_only`; same-tick cognition
cannot recapture it. Disabled cognition does not prevent this non-model cycle.

The adapter `sentientos.world_state_epistemic_evidence_adapter:v1` binds snapshot
ID/digest, fact ID, source ID/kind, observation time, rule ID, and proposition
ID/digest. Relations are configured, never inferred from prose. Unknown dependency
is conservative; independence requires an explicit basis. The frozen qualitative
rule maps support-only and contradiction-only evidence to provisional stances,
mixed evidence to contested, and wholly stale evidence to suspended. Position is
not truth, candidate is not authority, and mutation is not permission.

The runtime has no model invoker, proposition registration, calibration mutation,
background thread, or cadence. Immutable custody and admission ledgers provide
restart truth: exact existing bindings are not re-appended and an incomplete state
stage requires a fresh admission against the current predecessor.

This composition is not production sensor evidence, beneficial learning,
objective truth, or improved intelligence.
