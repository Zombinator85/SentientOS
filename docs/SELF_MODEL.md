# Self-model surfaces

SentientOS has two deliberately separate families that have historically used the
term “self-model.” They are not interchangeable.

## Production experimental composition

The operator-facing production self-reflection campaign composes the bounded
prior-tick self-model projection and external deterministic scorer with the
existing live resident A→B→A transition machinery. It preregisters exact model,
state, assessment, transition, and campaign custody and fails closed with a
machine-readable readiness artifact before effects. See
[`development/production_self_reflection_campaign.md`](development/production_self_reflection_campaign.md)
for the protocol, operator commands, evidence-posture derivation, and explicit
non-claims. This capability does not itself establish that a real production
trial occurred or support psychological, consciousness, sentience, learning, or
improvement claims.

## Legacy Glow self-state

`sentientos/glow/self_state.py` owns the compatibility `/glow/self.json` file (or
`$SENTIENTOS_DATA_DIR/glow/self.json`). It is a library-level mutable scratch
state for mood, confidence, attention, generated-goal context, and narrator
summaries. Its baseline/drift scripts fingerprint that implementation schema.
It is not composed into the default `sentientosd` maintenance path, is not an
evidence ledger, and carries no claim-level World-State provenance.

Earlier versions of this page described `identity`, `capabilities`,
`safety_flag`, `introspection`, `validation`, and `updated_at`. That description
does not match the live `DEFAULT_SELF_STATE`; it was documentation drift, not an
additional supported schema. The compatibility implementation and its tests
remain unchanged rather than being silently modernized into a different trust
contract.

## Evidence-bound longitudinal self-model

`sentientos.longitudinal_self_model.LongitudinalSelfModelOwner` is the modern
substrate for factual claims about the persistent causal system. It consumes an
already validated `WorldStateSnapshot`; it does not invoke a model or accept
free-form reflection. Each bounded claim records:

* a content-derived claim identity and stable subject/predicate key;
* structured value, category, lifecycle stage, and temporal scope;
* exact fact, source, source-digest, snapshot, and observation-time bindings;
* freshness, contradiction, evidence strength, and current/historical/
  withdrawn status;
* first/last supported generation and tick;
* supersession links; and
* software generation, cognitive-model identity, and developmental-history
  boundary when those values exist in authenticated source payloads.

The initial deterministic vocabulary is intentionally narrow: lifecycle
disposition plus explicit software/runtime generation, cognitive-model identity,
developmental-history boundary, configuration/capability identity, and a proven
observed consequence. An `observed_consequence` is projected only when the
World-State fact says the effect was proven. Authority, permission, policy,
goals, adoption, consciousness, sentience, identity continuity, learning,
improvement, and model-authored/reflection claims are rejected rather than
converted into facts.

### Reconciliation and custody

Reconciliations are immutable, digest-bound JSON records in a generation-ordered
journal. The writer uses the repository's atomic JSON writer. A repeated exact
snapshot returns the existing reconciliation, while a snapshot identity reused
with different bytes fails closed. Startup reconstructs and verifies the whole
digest and parent chain before writing.

A changed value supersedes the previously current value but retains it as a
historical claim. Disappearing evidence becomes `withdrawn`/`stale`, not false.
Old observations are historical rather than current. Simultaneous incompatible
values and World-State conflict bindings remain explicit contradictions; neither
confidence nor latest prose selects a winner. The source snapshot and its source
artifacts are read-only inputs and are never rewritten by reconciliation.

Every reconciliation and claim carries an all-false authority map. Projection is
description, not admission, policy, permission, adoption, effect completion, or
current truth by declaration.

### Runtime and cognition boundary

The causal ordering is source proof/observation → World-State → longitudinal
self-model → possible later developmental interpretation. `sentientosd` now has
an opt-in `SENTIENTOS_LONGITUDINAL_SELF_MODEL_CONFIG` composition. Its exact v1
configuration names an absolute custody root, enablement, cognitive-consumption
enablement, a 1–32 claim limit, an exact allowed-predicate list, and installation
identity. Absence remains inert. Explicit configuration reconstructs the entire
journal at startup and fails closed rather than replacing corrupt custody.

The cognitive projection is a deterministic read-only selection bound to one
exact reconciliation. It carries claim semantic digests, status, freshness,
contradiction, evidence strength, source identities, software/model/history
context, and an all-false authority map. Current evidence, prior self-model, and
developmental history remain three separate prompt objects: World-State is
current external evidence; the longitudinal self-model is evidence-bound factual
history; developmental history is prior interpretation; self-assessment is the
current stochastic reasoning over them. None equals authority.

Cognition for tick N runs before reconciliation of World-State N and can receive
only a projection whose source tick differs from N. Receipts bind its exact
reconciliation, generation, claims, current projection, history, model, and
generation configuration. This temporal firewall prevents reflection from
manufacturing the factual substrate it then cites as proof of itself.

The bounded intervention protocol preregisters present/withheld/restored order
without retries. Its external exact-key scorer measures supported correctness,
unsupported assertion, abstention, provenance, contradiction, and stale/current
handling. Output difference proves only changed output; negative and null results
remain valid, and a model answer cannot certify its own score.

The journal survives replacement of the software or cognitive model interpreting
it because its identities and verification depend on canonical evidence bytes,
not narrator state. This establishes the causal substrate needed to ask what was
represented, what changed, and what evidence followed. It does not establish
calibrated autonomous self-reflection, causal explanation beyond cited evidence,
psychological continuity, consciousness, learning, or improvement. Those require
runtime composition plus independently scored calibration and production
longitudinal trials.
# Embodiment evidence

The longitudinal owner now recognizes a bounded embodiment vocabulary for body,
asset, rig and renderer identity; body generation; sensor presence/health;
actuator availability; and separately commanded, renderer-reported, and
independently observed pose/expression. These claims retain World-State fact and
source identities, digest, freshness, contradiction, and supersession. They remain
all-false authority and become cognitive context only through the existing
prior-tick projection firewall. See
`docs/architecture/embodiment_self_observation_bridge.md`.
