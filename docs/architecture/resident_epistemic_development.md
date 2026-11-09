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

For explicitly selected developmental-history runs, the daemon routes the exact
run ID and digest represented in its validated same-tick World-State snapshot
through `process_verified_task_family_run`. The run owner rechecks the complete
scored protocol and derives the relation from its frozen comparison; generic
World-State adaptation does not duplicate that evidence. Run events later than
the daemon tick are ineligible. The resulting owner state remains next-tick-only
and is available to canonical plan-only allocation after reconstruction. Missing
or mismatched selected run evidence, including evidence whose event time is later
than the daemon tick, remains explicitly unresolved and does not create an
epistemic position.

The development companion can opt into this same owner without introducing a
second epistemic store. Its launcher composes the runtime only when both
`SENTIENTOS_EPISTEMIC_STATE_CONFIG` and
`SENTIENTOS_EPISTEMIC_DEVELOPMENT_CONFIG` are explicitly supplied. After an
operator-confirmed developmental cycle has run resident cognition and its
developmental writeback, the bridge submits that exact cycle snapshot to the
configured epistemic runtime. The later cognition projection reads the same
persistent state owner, so the update is eligible only in a subsequent cycle.
The cycle response reports epistemic status and evidence/state receipt identifiers
separately from developmental-history and self-model receipts. If this optional
owner fails, the already completed cognitive writeback remains intact and the
epistemic result is reported as degraded.

Without the development configuration, the companion performs no epistemic
mutation and reports `not_configured`. A configured but disabled runtime reports
`disabled`. These paths do not enable unattended desktop capture: the existing
per-message screen opt-in and owner admission rules remain in effect.

The runtime has no model invoker, proposition registration, calibration mutation,
background thread, or cadence. Immutable custody and admission ledgers provide
restart truth: exact existing bindings are not re-appended and an incomplete state
stage requires a fresh admission against the current predecessor.

This composition is not production sensor evidence, beneficial learning,
objective truth, or improved intelligence.
