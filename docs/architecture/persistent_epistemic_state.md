# Persistent epistemic state

The bounded resident lifecycle is specified in
[`resident_epistemic_development.md`](resident_epistemic_development.md): explicit
World-State rules drive separately admitted evidence and CAS state stages, and
resulting positions become cognitive context only on a later tick.

SentientOS now distinguishes five longitudinal substrates: World-State is current sourced evidence; the self-model is an evidence-bound representation of system condition; developmental history is retained interpretation; canonical memory is retained experience/user/context under memory law; and epistemic state is a persistent system-owned position over an explicit proposition. Authority remains permission to decide or act. None substitutes for another.

## Invariant and custody

**No epistemic-state delta without an attributable epistemic update event.** `PersistentEpistemicStateOwner` uses an explicit custody root, immutable content-addressed proposition and evidence records, immutable state generations, and a paired append-only event chain. Reconstruction checks every digest, predecessor, and paired event. Advancement is compare-and-swap; stale proposals fail rather than rebasing. There is no ambient discovery or legacy import.

On Windows, a missing store root may be created as one child beneath an
existing private-ACL parent; missing ancestors and broadly accessible parents
are rejected. The owner verifies the inherited ACL and parent identity before
creating its private child collections. Immutable records use the native
handle-bound no-replace publisher;
identity separators are encoded in portable file names. A root-identity-bound
mutex serializes compare-and-swap, and recovery completes storage-only
transaction pairs while leaving admission-bound incomplete pairs untouched for
separate admission-aware recovery; the storage owner does not recreate them from
state alone. The runtime test demonstrates interrupted
publication recovery, later contradiction revision, restart reconstruction, and
the resulting contested evidence packet. This establishes custody and context
composition with controlled records; it does not establish truth or beneficial
real-model adaptation.

The separately admitted mutation controller also writes Windows operation
intents and mutation receipts through the native publisher when its receipt root
and child collections already exist with private ACLs. Recovery can derive a
missing receipt only from the exact verified intent, admission, and committed
state; it never replays an interrupted evidence append or state transition.
When epistemic development is explicitly enabled, companion startup creates
those folders beneath the existing private cognition state root and verifies
each inherited ACL. Controller construction remains non-mutating; a missing or
broad parent prevents initialization.

A proposition identity hashes a bounded semantic key: schema, namespace, subject, predicate, bounded object, polarity, qualifiers, temporal scope, context scope, and class. Display text is excluded. Meaning changes create a new proposition connected by `refines`, `narrows`, `broadens`, `supersedes`, `contradicts`, or `related_to`; old evidence stays on its original proposition.

Evidence bindings retain exact source identity and digest, schema/class, observation time, relation, freshness, reliability posture, withdrawal, and one of `same_source_derivation`, `shared_upstream_evidence`, `repeated_observation`, `independently_sourced_observation`, `duplicate_alias`, or `unknown_dependency`. Mechanical posture reports absence, support, contradiction, mixed evidence, staleness, withdrawal, and dependency limitations. It is not a vote or truth oracle.

Positions use `unknown`, `suspended`, `provisionally_supported`, `supported`, `contested`, `provisionally_contradicted`, `contradicted`, or `superseded`. Confidence is absent by default. A numeric representation is permitted only as an explicitly structured value bound to its update rule, assumptions, dependence model, prior, and result; the owner supplies no universal weights.

Update reasons include initialization, new evidence, withdrawal, contradiction, duplicate correction, dependency correction, reliability revision, proposition refinement, update-rule correction, calibration outcome, and operator/error correction. This permits a correction without new external evidence and permits an attributable no-op. Model candidates remain proposals checked against exact predecessor and evidence custody; the deterministic owner commits.

Operator assertions entering through World-State `operator_input` sources are
adapted as `contextualizes` evidence with unknown dependency and the
`operator_assertion_unverified_context_only` reliability posture. Even a
configured rule that requests support or contradiction cannot turn a reported
correction directly into a directional position update. A later update needs a
separate source adapter that establishes the applicable evidence relation and
provenance; the assertion alone remains useful context for cognition.

The bounded mutation controller implements two independent transactions. An explicit source proof must exactly match an evidence binding before an exact evidence-stage admission can append it and produce an immutable receipt. A canonical candidate then binds the proposition, nullable predecessor (including a genuine `None` initialization predecessor), exact evidence set, stance, reason, rationale, uncertainty, model identity, schema, and all-false authority. A different exact state-stage admission permits deterministic validation and owner-level CAS. Neither stage accepts the full capability envelope or the other stage's effect set.

## Composition and boundaries

Resident cognition receives four separately typed channels: current World-State evidence, prior self-model, prior epistemic state, and developmental history. The epistemic projection binds proposition/state identities, generations, and evidence-set digests. Before inference, the owner verifies custody and captures the exact immutable update/state inventory as an epistemic epoch; only paired states in that capture are eligible. Update ticks order generations inside that epoch, while the daemon's string tick is never parsed, hashed, or treated as epistemic chronology. A second inventory comparison fails closed on concurrent advancement. Current evidence outranks a stale prior for current-condition reasoning while both remain visible.

Version 8 semantic projections also carry verified, digest-bound proposition
relations when both endpoints have eligible prior positions and at least one
endpoint is selected. The relation is repeated in each selected endpoint's
packet and remains a recorded historical link, not truth or authority. Context
assembly keeps `contradicts` and `supersedes` endpoint packets together when
both are in the projection. If the state cap omits one endpoint, its canonical
proposition meaning accompanies the relation and its state remains summarized
as omitted; the projection validator rechecks that proposition identity. If
the input budget cannot carry a projected pair, it omits the pair and records
the relation digest. Prompt instructions explicitly forbid treating an omitted
relation or endpoint as absent or resolved. Older projection versions retain
their existing identity formats. Deterministic fixtures establish projection
and budget behavior; real-model use remains unverified.

Ordinary companion responses now return `epistemic_state_ids` for stored
positions whose complete semantic packets reached the prompt and materially
influenced an answer. The parser checks each ID against those delivered packets,
and the durable cognition
observation records those citations beside the projection's state IDs and
digests. This makes claimed use observable across the response lineage; it does
not prove that the model reasoned correctly or make the cited position evidence,
truth, or authority. A deterministic matched A/B/A integration fixture verifies
that citations appear with the state, disappear when withheld, and return when
restored, while keeping answer text fixed.

Embodied prediction and maintenance post-adoption comparisons can be adapted only through explicit evidence adapters. Matching observations support and mismatches contradict; renderer/model self-report cannot masquerade as independent corroboration. Calibration custody resolves the exact forecast state, requires that it belongs to the same proposition and predates resolution, and requires proposition-owned source bindings. A foreign proposition's state or binding cannot be smuggled into calibration merely because it exists in custody.

Calibration records enter a meaning-bearing cognitive projection only after
their exact calibration ID and digest are linked to a `calibration_outcome`
update event. Unreviewed records contribute only to a bounded omitted-identity
count; their label and outcome text remain unavailable to later reasoning. The
proposed calibration-review definition is not registered in the canonical
authority catalog yet, so the runtime review path currently fails closed unless
an explicitly injected review authority is available. See the
[calibration runtime authority proposal](../development/resident_epistemic_calibration_runtime_authority_proposal.md).

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

The strongest supported claim is structural and repository-bounded: persistent positions are model-independent, reconstructable, attributable, provenance-preserving, separately admitted for mutation, and explicitly composed into later cognition without authority. This does not establish objective truth, Bayesian optimality, beneficial learning, or real model-replacement performance. The next frontier is composed observation-adapter admission, governed candidate construction, runtime cadence, production ingestion, and repeated longitudinal measurement—not automatic writeback or additional confidence arithmetic.
