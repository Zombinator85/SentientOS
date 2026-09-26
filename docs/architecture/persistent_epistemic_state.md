# Persistent epistemic state

SentientOS now distinguishes five longitudinal substrates: World-State is current sourced evidence; the self-model is an evidence-bound representation of system condition; developmental history is retained interpretation; canonical memory is retained experience/user/context under memory law; and epistemic state is a persistent system-owned position over an explicit proposition. Authority remains permission to decide or act. None substitutes for another.

## Invariant and custody

**No epistemic-state delta without an attributable epistemic update event.** `PersistentEpistemicStateOwner` uses an explicit custody root, immutable content-addressed proposition and evidence records, immutable state generations, and a paired append-only event chain. Reconstruction checks every digest, predecessor, and paired event. Advancement is compare-and-swap; stale proposals fail rather than rebasing. There is no ambient discovery or legacy import.

A proposition identity hashes a bounded semantic key: schema, namespace, subject, predicate, bounded object, polarity, qualifiers, temporal scope, context scope, and class. Display text is excluded. Meaning changes create a new proposition connected by `refines`, `narrows`, `broadens`, `supersedes`, `contradicts`, or `related_to`; old evidence stays on its original proposition.

Evidence bindings retain exact source identity and digest, schema/class, observation time, relation, freshness, reliability posture, withdrawal, and one of `same_source_derivation`, `shared_upstream_evidence`, `repeated_observation`, `independently_sourced_observation`, `duplicate_alias`, or `unknown_dependency`. Mechanical posture reports absence, support, contradiction, mixed evidence, staleness, withdrawal, and dependency limitations. It is not a vote or truth oracle.

Positions use `unknown`, `suspended`, `provisionally_supported`, `supported`, `contested`, `provisionally_contradicted`, `contradicted`, or `superseded`. Confidence is absent by default. A numeric representation is permitted only as an explicitly structured value bound to its update rule, assumptions, dependence model, prior, and result; the owner supplies no universal weights.

Update reasons include initialization, new evidence, withdrawal, contradiction, duplicate correction, dependency correction, reliability revision, proposition refinement, update-rule correction, calibration outcome, and operator/error correction. This permits a correction without new external evidence and permits an attributable no-op. Model candidates remain proposals checked against exact predecessor and evidence custody; the deterministic owner commits.

## Composition and boundaries

Resident cognition receives four separately typed channels: current World-State evidence, prior self-model, prior epistemic state, and developmental history. The epistemic projection binds proposition/state identities, generations, and evidence-set digests. Its source tick must precede the cognition tick, preventing same-tick self-certification. Current evidence outranks a stale prior for current-condition reasoning while both remain visible.

Embodied prediction comparisons and attributions can be adapted only through the explicit independent-observation adapter. Matching observations support and mismatches contradict; renderer self-report cannot masquerade as independent corroboration. Calibration records bind forecast state, observed outcome, comparison, and exact evidence without a universal score.

Runtime construction is inert unless `SENTIENTOS_EPISTEMIC_STATE_CONFIG` names an explicit custody root, namespace allowlist, projection bound, and cognition-consumption switch. Read-only queries are available through owner methods (`proposition`, `bindings`, `current_state`, and `verify`); mutation remains controller-only.

## Existing surfaces

| Surface | Classification | Relationship |
|---|---|---|
| World-State board/sources | current reusable primitive | current sourced evidence, never overwritten by belief |
| longitudinal self-model | current reusable primitive | distinct prior system representation |
| developmental cognition/writeback | current reusable primitive | consumes the fourth substrate; history remains interpretation |
| embodied consequence | current reusable primitive | first explicit modern evidence adapter |
| canonical/selective memory | current reusable primitive | retention law, not epistemic state |
| Phase-56 claim/evidence ledgers | compatibility/supporting, conversation-only | explicit provenance adapters may nominate material; never auto-promoted |
| `EpistemicLedger` | legacy, uncomposed, UI-facing heuristic | process-local list and numeric vocabulary are not custody |
| `BeliefVerifier` | legacy heuristic/diagnostic | its fixed weighting is not a canonical update rule |
| epistemic status/stance/preflight/research gates | compatibility/supporting or conversation-only | bounded vocabulary/gating, not persistent ownership |
| provisional assertion/evidence diagnostic | diagnostic | evidence inspection, not committed position |
| discernment calibration | compatibility/supporting | no automatic import; explicit source adapter required |

`legacy confidence heuristic != canonical epistemic update`.

Evidence is not belief. Belief is not truth. Belief is not authority. Belief is not policy, goal, permission, effect admission, adoption, memory-retention authority, or World-State replacement. Model proposes; system records. Persistent epistemic state belongs to the longitudinal causal system, not the currently loaded cognitive worker.

The strongest supported claim is structural and repository-bounded: persistent positions are model-independent, reconstructable, attributable, provenance-preserving, and available to later cognition. This does not establish objective truth, Bayesian optimality, beneficial learning, or real model-replacement performance. The next causal bridge is an operator-authorized production observation adapter and longitudinal outcome study, not additional confidence arithmetic.
