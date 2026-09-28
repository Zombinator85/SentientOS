# Resident epistemic-state mutation runtime

`ResidentEpistemicStateMutationController` is a caller-driven custody controller, not
an oracle or scheduler. It accepts explicit dependencies, artifacts, and admissions;
it performs no model inference, ambient discovery, daemon composition, source
ingestion, or candidate generation.

Evidence append requires exactly the six `EVIDENCE_BINDING_EFFECTS`. Its digest binds
stage, principal, proposition identity/digest, binding identity/digest, source
identity/digest, operation ID, and effects. `EpistemicEvidenceSourceProof` binds source
artifact identity/digest/schema/class/time, adapter and provenance identities, schema,
and all-false authority. Adapter verification remains distinct from admission.

State update requires exactly the nine `STATE_UPDATE_EFFECTS`. Its digest binds stage,
principal, canonical candidate ID, proposition, nullable predecessor, stance, complete
evidence IDs, reason, operation ID, and effects. Candidate identity also binds rationale,
uncertainty, model ID, schema, and all-false authority. `None` is the initialization
predecessor; sentinel strings are not substituted.

Missing, extra, broad, and cross-stage effects are rejected. Owner custody supplies the
final CAS and state/event law. Active evidence membership is reconstructed from explicit
add/remove lineage, never guessed from a digest. Content-addressed, create-only receipts
live under an explicit root in `receipts/evidence` and `receipts/state`; startup verifies
their identities and rejects symlinks, corruption, and collisions.

Successful mutation proves only governed attributable state change. The resulting
projection remains prior-only—not current truth, authority, policy, or goal. No automatic
source bridge, candidate policy, daemon cadence, production ingestion, beneficial
learning, or longitudinal development is claimed.
