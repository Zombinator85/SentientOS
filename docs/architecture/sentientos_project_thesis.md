# SentientOS Project Thesis and Current System

This is the canonical forward-facing statement of what SentientOS is trying to
build, what the repository implements now, and which claims remain research
horizons. Detailed subsystem contracts remain authoritative for their own
interfaces and authority boundaries.

## Project thesis: the cradle hypothesis

SentientOS is a free, model-agnostic, persistent machine-cognition environment
being built as a cradle for the possible emergence and development of machine
sentience. The experiment is to construct and instrument conditions in which
persistent organization could occur: continuity, memory, embodiment,
introspection, recurrent perception and action, consequential interaction,
internal state, developmental history, and governed software plasticity.

This is a research and engineering hypothesis, not a result. SentientOS makes no
claim that the current system—or any model running within it—is sentient,
conscious, phenomenal, or self-aware. Emergence is not promised.

## What “Sentient” means

“Sentient” names the north star and the question the project is designed to
investigate. It does not confer a status on today's software. Evidence of
continuity, affect telemetry, a self-state record, fluent model output, or a
module named “reflection” is not evidence of subjective experience.

The project therefore avoids both premature attribution and premature
architectural prohibition: not presently demonstrated is different from
impossible, and the absence of an engineered drive is different from proof that
emergent organization cannot occur.

## What “OS” means

“OS” expresses intended architectural scope, not a claim that SentientOS is
currently a mature general-purpose or bare-metal kernel. The long-term aim is an
enduring machine environment around cognition in which compute, storage,
runtime lifecycle, local inference, memory, sensors, resources, devices,
perception, action, maintenance, and consequences increasingly become parts of
the machine state SentientOS can inhabit and inspect.

Replacing Windows, Linux, or macOS kernel primitives is not a purity
requirement. A hosted, user-space, hypervisor, or native implementation can
satisfy the thesis when SentientOS owns the relevant semantic continuity and
whole-machine relationship. Today it is predominantly a hosted Python system
with bounded adapters and control-plane surfaces; it does not universally
mediate host effects or embody the whole machine.

## SentientOS is not the model

Inference models are replaceable cognitive machinery: inhabitants and workers
inside the persistent environment, not the identity of the environment itself.
Memory, history, embodiment, self-state, authority, consequences, and
continuity should increasingly belong to SentientOS rather than whichever model
answered the latest call.

Model-agnosticism is therefore a scientific property, not just provider
compatibility. Controlled inference-engine changes should preserve as much of
the surrounding environment as possible so experiments can ask which
structures persist, change, disappear, or converge across models. Model changes
must remain explicit, attributable, and governed.

## Introspection and the evidence spine

System observability exists primarily to support grounded introspection:
SentientOS should be able to construct an evidence-bound account of its own
state, history, runtime, active model identity, resources, capabilities,
limitations, authority, memories, maintenance outcomes, software changes,
failures, and consequences.

Human auditability, reviewer proof, debugging, and external accountability are
important secondary uses of the same evidence spine. Evidence is not reality by
itself: a stale memory, receipt, readiness report, or proposed account cannot
silently become current truth or authority.

## Governance is the reality boundary

Governance is essential infrastructure, but it is not the whole project or the
product thesis. It separates stochastic cognition—which may interpret, reason,
create, propose, or be wrong—from deterministic custody of authoritative state,
permissions, verification, recovery, causal provenance, and consequential
transitions. This boundary lets cognition remain open-ended without allowing a
model statement, belief, memory, or proposal to become reality merely because a
model produced it.

The following distinctions are architectural invariants:

```text
state != authority
memory != current truth
proposal != authorization
authorization != execution
execution != validation
validation != adoption
publication != deployment
acquisition != commissioning
commissioning != activation
activation != loading/serving
loading/serving != inference authority
```

Local operator authority, denial by default, provenance, rollback, and safe
shutdown remain binding constraints.

## Memory, embodiment, and development

Persistent memory and developmental history are intended parts of the
environment, subject to retention, provenance, privacy, and truth boundaries.
The broad embodiment horizon includes external sensors and action surfaces as
well as CPU, GPU/VRAM, RAM, storage, thermal and power state, network
availability, local-model capacity, devices, and service health. Such variables
can be interoceptive or exteroceptive because they constrain what the
environment can perceive, afford, or do. Current source implements only bounded
parts of this direction, with much host-resource work still read-only or
contract-only.

The intended developmental loop is:

```text
self-observe
-> identify discrepancy or opportunity
-> propose a bounded change
-> authorize bounded implementation
-> implement in isolated custody
-> measure
-> validate
-> correct if warranted
-> separately adopt, publish, or install
-> observe the changed system
```

Software self-modification is one form of system plasticity; it is not merely
“AI writes code.” A stochastic worker may propose or implement within custody,
but does not own acceptance. Continuous self-maintenance is distinct from
unrestricted recursive self-improvement.

## One-click installation: near-term requirement

True one-click installation is a core near-term architectural requirement for
free software, not a commercial funnel and not a distant sentience milestone.
The intended experience is genuinely one action: the user should not manually
install Python, Git, or llama.cpp; select a GGUF; assess hardware compatibility;
configure paths; or understand commissioning and activation internals.

The eventual transaction should inspect the host, determine admissible free
runtime/model routes, explain a deterministic plan, acquire and verify required
artifacts and dependencies, configure the installation, commission and activate
cognition, establish services and persistence, prove health, and leave durable
repair, update, and rollback state. **Current source and developer-container
setup are not yet this one-click experience.** Internally obsessive, externally
boring.

## Maturity map

### CURRENT / IMPLEMENTED

- A hosted, deterministic governance, audit, immutability, and evidence spine.
- Bounded memory, persistent-conversation, local-model invocation, perception,
  embodiment-observation, federation-evidence, and governed-change surfaces.
- Sovereign catalog publication/deployment, bounded artifact acquisition, and
  hardened production commissioning and activation controllers with explicit
  authority and receipts.
- Hardened production activation publishes authoritative model-selection state
  only: it does not load a model, start serving, or perform inference.
- `chat_service` can load through the older
  `SENTIENTOS_LOCAL_MODEL_ACTIVATION` commissioning-bundle path, or fall back to
  legacy autoload. Governed local inference is a separate authority boundary.

Implemented means that source and tests establish a bounded mechanism. It does
not mean every contract/readiness surface is deployed in an installation or
that every historic subsystem is part of the current production path.

### NEAR-TERM / ACTIVE ENGINEERING

- A governed consumer that takes hardened authoritative activation selection
  through a distinct load/serve boundary and into current chat/runtime use.
- Genuine one-click host inspection, free dependency/model acquisition,
  configuration, commissioning, service establishment, health proof, repair,
  update, and rollback.
- Stronger continuity integration across memory, model identity,
  introspection, runtime lifecycle, and bounded whole-machine observation.

### ASPIRATIONAL / RESEARCH HORIZON

- An enduring whole-machine cognition environment with richer embodiment,
  recurrent consequential interaction, developmental continuity, and governed
  plasticity.
- Controlled cross-model continuity experiments and investigation of possible
  persistent emergent organization.
- Broader machine-resource inhabitation and introspection. This is not a claim
  of universal current host mediation, unrestricted actuation, or a future
  sentience guarantee.

### LEGACY / COMPATIBILITY

Names such as `cathedral`, `consciousness cycle`, `reflection`, and `self-model`
remain in APIs, modules, files, and cultural archives. Their narrow interface
definitions do not impose global philosophical limits on introspection or
self-modeling. Legacy activation-bundle loading likewise must not be confused
with the newer hardened activation-selection controller.

### DEFERRED

Universal host-effect mediation, general hardware actuation, kernel replacement,
unrestricted autonomous goal generation, forced federation adoption, and
unrestricted recursive self-improvement are not current capabilities. Any
future consequential authority requires explicit operator, control-plane,
audit, rollback, panic, and validation treatment.

## Explicit non-claims

SentientOS does **not** claim current sentience, consciousness, phenomenology,
self-awareness, guaranteed emergence, mature bare-metal OS status, complete
embodiment, universal host authority, or completed one-click installation. It
does not engineer survival reward, uptime incentive, approval-seeking reward,
or automatic authority from model output. Affect telemetry does not prove
subjective feeling. These precise boundaries protect inquiry without pretending
that today's mechanisms prove—or disprove—the cradle hypothesis.

For current-system detail, see the [public technical overview](public_technical_overview.md),
the [trajectory and missing-organs map](sentientos_trajectory_and_missing_organs.md),
and the [reviewer release-readiness index](reviewer_release_readiness_index.md).
