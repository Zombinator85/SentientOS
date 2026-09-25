# Resident cognitive model transition experiment authority

## Registration posture

`resident_cognitive_model_transition_experiment` remains the existing operator-approved definition in `memory_context_reflection`, for principal `deterministic_resident_cognitive_model_transition_controller`. Its definition digest is `83f279d23060d6d378005590c0e0b1311efd826dab91fab1da8b02c090f73f88`; the digest-bound approval evidence digest is `a3a90aaec88c18a048644c665f21af2ed5851c4cd521285bad2e06bd7c4ba828`. The bounded in-process runner implements only that registered effect set. Registration itself still grants no capability or runtime authority.

The canonical Python definition registers exactly fourteen future effects: exact operator-approval evidence read; exact preregistered protocol read; exact current resident-serving-state read; exact developmental-history boundary-snapshot read; bounded cognition-quiescence set and exact observation; exact separately admitted activation-receipt read; exact transition-stage resident-serving-binding write; exact successor-serving-state read; bounded cognition resume; exact restored-predecessor observation; transition-journal append; transition-receipt write; and read-only health. It permits no activation mutation, model load, inference, developmental-history append, canonical-memory mutation, acquisition, or commissioning.

## Preregistered protocol and stages

Before the first effect, an immutable protocol must bind schema/version, ID/digest, installation, exact predecessor A, successor B and restored-A `CognitiveModelIdentity`, both hardened commissioning receipts, initial A activation digest/generation, initial resident A session/receipt, initial history-boundary digest, phase order, only A -> B and B -> A, each expected prior activation, exact stage serving-operation identities, epoch/failure/no-retry policies, nonclaims, and `grants_authority=false`. Protocol != approval, authority, or occurrence.

The durable state machine is staged: `predecessor_a_epoch_current`, `a_to_b_transition_requested`, `a_quiesced`, `b_activation_committed`, `b_serving_bound`, `b_epoch_resumed`, `b_epoch_observed`, `b_to_a_restoration_requested`, `b_quiesced`, `a_restoration_activation_committed`, `restored_a_serving_bound`, `restored_a_epoch_resumed`, `post_restoration_observed`, and `experiment_complete`. Names may be refined later, but one explicit invocation advances at most one effectful stage. There is no background cadence, retry loop, stage loop, or automatic A -> B -> A completion.

## Bounded runtime composition

The runner consumes an exact per-stage approval bound to capability, principal, protocol and transition identities, requested stage and prior phase, journal head, installation, A/B/restored-A identities, current activation/session/history boundary, correlation and operation identity, validity interval, and synthetic posture. Production rejects synthetic approval. This approval grants no activation, serving, or inference authority.

The journal is authoritative on construction. It validates the full hash chain and stage order and reconstructs completed, attempted-but-unproven, externally-effected-but-incompletely-recorded, failed, and interrupted posture. Failed or unresolved stages remain permanently non-replayable when the Python controller is reconstructed. There is no retry or rollback. Exact subordinate custody may establish that an effect occurred, but missing transition completion evidence still leaves the experiment interrupted.

Every A -> B and B -> A mutation remains owned by `local_model_production_activation`, with independent operator approval, `AuthorityClass.MODEL_ACTIVATION` admission, and expected-prior-state CAS. This authority only reads its receipt. Every load remains owned by `resident_cognitive_model_serving` with separate eligibility and `AuthorityClass.MODEL_SERVING` admission. Every post-resume cognition call remains separately `AuthorityClass.LOCAL_MODEL_INFERENCE` admitted; resume performs no inference. Normal history append remains owned by `resident_developmental_writeback`; a boundary snapshot or transition journal is not developmental-history mutation.

## Transition-stage resident-serving binding

The immutable `sentientos.resident_cognitive_transition_stage_serving_binding:v1` object binds protocol ID/digest, transition/stage IDs, installation, committed activation-state digest/generation, activation receipt ID/digest, expected model identity, exact serving-operation ID, and resident-serving capability ID. It states `grants_model_serving=false`, `grants_inference=false`, and `grants_activation=false`. The stable serving slot consumes it only through a transition-specific bind that also verifies the exact live quiescence token/generation and current replacement session identity. Ordinary startup binding is unchanged.

Startup configuration remains bound to one serving-operation identity, one exact expected activation digest, and one configuration digest. It is never rewritten from A to B or changed to `current`, `latest`, default, wildcard, or implicit following. Binding != startup configuration, serving authority, model load, or current session.

## Quiescence, resume, and failure truth

Quiescence prevents a new developmental cycle and starts only at a bounded safe point with no inference/writeback in flight. Its proof binds owner, last tick, observation/writeback receipts, history record-set digest, serving session, activation state, token/generation, and no-in-flight status. It does not change history or unrelated chat/maintenance and grants no activation authority.

The gate is intentionally process-local. Journal evidence cannot recreate an old live token after process death. Reconstruction may continue only when supplied the same live gate and it proves the exact journaled generation/token; otherwise health is blocked/interrupted and resume is forbidden.

Resume requires exact intended activation and stage serving current, loaded identity equality, no unresolved earlier custody, and the exact legal journal prefix. If activation is denied after quiescence, remain interrupted with A canonical. If A -> B commits but B serving fails, persist `b_activation_committed_serving_unavailable`, keep B canonical and cognition stopped, and never reactivate A automatically. Without restoration approval, B remains current. If B -> A commits but restored-A serving fails, keep A canonical and cognition quiesced. Cleanup != rollback; rollback != restoration; restoration != retry. No automatic retry, rollback, restoration, fallback, or replay is permitted.

Production chat is outside this experiment. Its own law may mark it stale after activation drift; the transition controller cannot close, re-establish, rebind, mutate its custody, or hide its staleness.

Restoration can establish exact A artifact/configuration/runtime serving again, custodied history survival, restored-A access to B-epoch records, and comparable behavior. It cannot establish a persistent subjective individual, model-independent identity, consciousness/selfhood continuity, improvement, sentience, or learning from output difference.

The synthetic rehearsal now uses authenticated isolated installation custody, real `activate_production()`, real resident-serving controllers, the real stable serving slot, governed local inference, resident developmental cognition, and resident developmental writeback. Deterministic fake workers enter only through the established worker-factory seam. Restored-A ordinary cognition retrieves the exact durable record written during B; the transition runner never injects or appends history itself.

The daemon maintenance facade now accepts at most one immutable, installation-custodied
operator request per explicit call after ordinary cognition.  Request presence grants no
authority and receipt custody prevents duplicate replay.  The exact packet, configuration,
status, and custody contracts are documented in
`resident_cognitive_transition_live_operator_ingress.md`.

The remaining bridge is real production temporal evidence using actual hardened
commissioned models. Recovery after daemon/process death, autonomous cadence, automatic
switching, and continuity/identity/consciousness/learning conclusions remain deferred.
