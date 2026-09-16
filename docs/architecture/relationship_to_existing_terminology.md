# Relationship to Established Technical Terminology

This page makes SentientOS legible beside established fields without converting
architectural resemblance into implementation status. Each entry states a
technical meaning, a relationship classification, repository evidence, the
important mismatch, and current maturity. Classifications are limited to:
`direct technical fit`, `subsystem-level fit`, `related architecture /
intellectual lineage`, `research-horizon relationship`, and `not currently
justified`.

Definitions were checked against the primary/foundational sources linked below
where available. Newer “agent OS,” “scaffold,” “self-evolving agent,” and AI4AI
language remains unsettled; it is used conservatively rather than as a product
category.

## 1. Persistent runtime

### Agent Operating System, operating architecture, scaffold, and harness

- **Definition.** Recent Agent-OS work generally places model calls within
  services for agents, memory, tools/resources, scheduling, communication, and
  lifecycle. A scaffold or harness is the model-facing code that assembles
  context, tools, control flow, and evaluation around an inference engine.
- **Classification.** **Related architecture / intellectual lineage** for an
  Agent Operating System; **subsystem-level fit** for scaffold/harness.
- **Evidence.** `sentientosd`, governed local-model serving, persistent
  conversation/memory, perception, authority, audit, host/resource surfaces,
  and maintenance generations persist beyond a call.
- **Difference.** SentientOS is currently a hosted Python environment, not a
  kernel or universal multi-agent resource mediator. “Harness” describes only
  its model-facing layer, not the persistent environment. The careful public
  term is **agent-operating environment related to AOS literature**.
- **Maturity.** Persistent bounded environment: **CURRENT / PARTIAL**; mature
  general-purpose AOS: **not currently justified**.

### Autonomic computing, self-managing systems, and MAPE-K

- **Definition.** IBM's autonomic blueprint organizes self-management as
  Monitor–Analyze–Plan–Execute over shared Knowledge (MAPE-K), with managed
  resources and touchpoints ([Kephart & Chess, 2003](https://doi.org/10.1109/MC.2003.1160055);
  [IBM autonomic architecture](https://www.ibm.com/support/pages/autonomic-computing-architectural-blueprint)).
  MAPLE-style legitimacy/meta-adaptation variants additionally ask who may
  change the adaptation process and under what governance.
- **Classification.** **Related architecture / intellectual lineage**.
- **Evidence.** Evidence collection, bounded maintenance formation,
  implementation, validation, repository adoption, successor derivation, and
  resident adoption form a governed feedback loop with authority records.
- **Difference.** Components are not represented as a canonical MAPE-K engine,
  and authority/adoption separations are stronger than a generic feedback loop.
  MAPLE-K is not claimed as implemented merely because legitimacy is explicit.
- **Maturity.** Bounded maintenance loop: **CURRENT / IMPLEMENTED BUT
  GOVERNED**; canonical MAPE-K/MAPLE-K conformance: **not currently justified**.

## 2. Cognitive organization

### Cognitive architecture

- **Definition.** A cognitive architecture specifies persistent computational
  structures and processes supporting cognition across tasks—not just one
  model call (see [Newell, *Unified Theories of Cognition*, 1990](https://psycnet.apa.org/record/1990-98487-000)
  and the [Soar architecture](https://soar.eecs.umich.edu/)).
- **Classification.** **Related architecture / intellectual lineage**.
- **Evidence.** Perception, memory/context, model reasoning, evidence-bound
  self/world state, reflection, action surfaces, and governed modification are
  composed around a persistent runtime.
- **Difference.** SentientOS does not claim a unified psychological theory or
  formal equivalence to Soar, ACT-R, or another canonical architecture.
- **Maturity.** Integrated organs: **CURRENT / PARTIAL**.

### Metacognition, metareasoning, and computational reflection

- **Definition.** Metareasoning reasons about reasoning and allocation;
  computational reflection lets a system represent and causally use aspects of
  its own computation ([Maes, 1987](https://doi.org/10.1145/38765.38821)).
  “Self-aware computing” is an engineering field concerned with runtime models
  of system state and adaptation, not phenomenal awareness.
- **Classification.** **Subsystem-level fit** for evidence-bound reflection;
  **related architecture / intellectual lineage** for self-aware computing.
- **Evidence.** Capability/runtime/model/resource and maintenance-generation
  records can inform bounded proposals and governed software change.
- **Difference.** Evidence can be stale or incomplete, and deterministic gates—not
  a self-description or model intuition—own effects. No perfect self-knowledge
  or phenomenal self-awareness is claimed.
- **Maturity.** **CURRENT / IMPLEMENTED BUT BOUNDED**.

## 3. Senses and social perception

### Affective computing and social signal processing

- **Definition.** Affective computing studies systems that recognize, model, or
  respond to affect ([Picard, 1997](https://mitpress.mit.edu/9780262661157/affective-computing/)).
  Social signal processing analyzes observable nonverbal/social signals such as
  face, voice, posture, and gaze ([Vinciarelli, Burgoon & Magnenat-Thalmann,
  2017](https://doi.org/10.1145/3057278)).
- **Classification.** **Subsystem-level fit**.
- **Evidence.** Facial/expression telemetry, audio/voice surfaces, gaze adapters,
  camera/vision observations, and longitudinal household evidence exist at
  differing bounded maturity.
- **Difference.** `observable signal != inferred psychological state != current
  truth != authority`. The code does not provide infallible emotion access.
- **Maturity.** **CURRENT / PARTIAL**.

### Gaze following, social attention, joint attention, and Theory of Mind

- **Definition.** Gaze following estimates another's direction of attention;
  joint attention requires coordination around a shared referent. Theory of
  Mind is a stronger attribution of mental states.
- **Classification.** Gaze/social attention: **subsystem-level fit**; joint
  attention and Theory of Mind: **not currently justified**.
- **Evidence.** Gaze-related adapters and multimodal observations exist.
- **Difference.** No repository proof establishes robust person–shared-referent–
  system coordination, and gaze detection is not mental-state attribution.
- **Maturity.** Gaze signals: **PARTIAL**; stronger terms: **not current**.

## 4. Memory and epistemics

### Episodic, semantic, autobiographical memory, and consolidation

- **Definition.** Episodic memory concerns situated events; semantic memory
  concerns generalized knowledge; consolidation stabilizes or reorganizes
  traces. Autobiographical memory longitudinally organizes self-relevant
  experience rather than merely storing records.
- **Classification.** Consolidation/distillation: **subsystem-level fit**;
  autobiographical memory: **related architecture / intellectual lineage**.
- **Evidence.** Persistent conversation, canonical fragments, provenance,
  selective retain/distill/capsule decisions, tomb intent/verification, and
  developmental and maintenance history support longitudinal organization.
- **Difference.** The repository does not claim human memory mechanisms or one
  monolithic autobiographical store; real distillation-to-live-memory mutation
  remains deferred.
- **Maturity.** Retrieval/retention and metadata custody: **CURRENT / PARTIAL**.

### Belief revision, truth maintenance, and epistemic state management

- **Definition.** A formal Truth Maintenance System maintains dependencies and
  justifications while revising beliefs; an ATMS manages assumption-labelled
  environments ([Doyle, 1979](https://doi.org/10.1016/0004-3702(79)90032-7);
  [de Kleer, 1986](https://doi.org/10.1016/0004-3702(86)90080-9)).
- **Classification.** **Related architecture / intellectual lineage**.
- **Evidence.** Provenance, truth qualification, contradiction/staleness
  posture, revision candidates, receipt gates, and `memory != current truth`
  implement belief-revision-oriented epistemic custody.
- **Difference.** No general formal justification/dependency-propagation engine
  is proven. SentientOS is **not a formal TMS or ATMS**.
- **Maturity.** Epistemic state management: **CURRENT / PARTIAL**; formal
  TMS/ATMS equivalence: **not currently justified**.

### Event sourcing

- **Definition.** Event sourcing stores state changes as the primary append-only
  system of record and reconstructs current aggregate state by replay.
- **Classification.** **Not currently justified** globally.
- **Evidence.** Ledgers, receipts, immutable/digest chains, and replayable
  evidence exist on bounded surfaces.
- **Difference.** Current authoritative state is not universally reconstructed
  from one primary event log. Append-only audit evidence alone is not event
  sourcing.
- **Maturity.** Limited ledger resemblance: **CURRENT**; global event-sourced
  architecture: **not claimed**.

## 5. Embodiment and environment

### Sensorimotor architecture, interoception, and exteroception

- **Definition.** Sensorimotor architectures connect sensing and action;
  interoception observes internal/body state, while exteroception observes the
  external environment.
- **Classification.** **Subsystem-level fit**.
- **Evidence.** Audio/screen/vision and Household Presence are exteroceptive;
  runtime, model, compute, memory, storage, thermal/power, and service-health
  observation provide a machine-interoceptive analogy; bounded GUI/file effects
  provide action surfaces.
- **Difference.** Adapter availability and authority vary, and most hardware
  actuation remains blocked. The analogy does not imply biological embodiment.
- **Maturity.** **CURRENT / PARTIAL AND GOVERNED**.

### Ambient/ubiquitous/context-aware computing, situation awareness, and world models

- **Definition.** Context-aware systems use sensed context to adapt service;
  situation assessment combines observations into a usable account of current
  conditions. A cognitive world model is a stronger predictive/causal
  representation.
- **Classification.** Context/situation evidence: **subsystem-level fit**;
  full world model: **not currently justified**.
- **Evidence.** Household Presence, host resources, context artifacts, and the
  read-only `world_state_evidence_board` compose provenance, staleness, and
  contradiction-aware evidence.
- **Difference.** The board is not decision authority or a demonstrated
  predictive world model.
- **Maturity.** Evidence custody: **CURRENT / IMPLEMENTED**.

### Active perception and active sensing

- **Definition.** Active perception selects what, how, when, or where to sense
  to reduce task-relevant uncertainty ([Bajcsy, 1988](https://doi.org/10.1109/5.5968)).
- **Classification.** **Not currently justified** as a general architecture.
- **Evidence.** Bounded requests and adapter selection exist on some surfaces.
- **Difference.** Passive telemetry and scheduled observation alone do not
  satisfy active perception.
- **Maturity.** **PARTIAL / RESEARCH TRAJECTORY**.

## 6. Household and social modeling

### User modeling, personalized agents, social memory, and longitudinal modeling

- **Definition.** User models represent user-relevant traits, preferences, or
  interaction history; social memory and longitudinal models organize repeated
  interactions over time.
- **Classification.** **Subsystem-level fit**.
- **Evidence.** **Household Presence**, person/profile surfaces, repeated
  observations, persistent conversation, selective memory, operator trend
  ledgers, and reflection artifacts compose fragmented bounded modeling.
- **Difference.** There is no single monolithic household mind model. The data
  model is not proven to be a **personal knowledge graph**.
- **Maturity.** **CURRENT / PARTIAL**; personal knowledge graph:
  **not currently justified**.

## 7. Authority and runtime assurance

### Reference monitor, capability security, and least privilege

- **Definition.** A reference monitor mediates every access, is tamper-resistant,
  and is small enough to analyze; capability security grants authority through
  unforgeable, delegable references. Least privilege limits authority to what is
  required ([Saltzer & Schroeder, 1975](https://doi.org/10.1109/PROC.1975.9939);
  [NIST SP 800-53 reference monitor](https://csrc.nist.gov/glossary/term/reference_monitor)).
- **Classification.** **Subsystem-level fit** / capability-security-oriented and
  reference-monitor-like on mediated surfaces.
- **Evidence.** Exact principals/effects, non-granting admissions, scoped leases,
  deterministic gates, denial, provenance, receipts, and operator authority.
- **Difference.** Global complete mediation, tamper resistance, and strict
  object-capability semantics are not established. SentientOS is **not claimed
  to be a formal global reference monitor**.
- **Maturity.** Bounded mediated surfaces: **CURRENT / IMPLEMENTED**.

### Runtime assurance, runtime verification, shielding, and Simplex

- **Definition.** Runtime assurance monitors operation and enforces constraints;
  Simplex specifically switches from a complex high-performance controller to
  a verified safety controller when safety may be violated ([Sha et al.,
  1998](https://doi.org/10.1109/2.681269)).
- **Classification.** Runtime-assurance-like: **subsystem-level fit**; Simplex:
  **not currently justified**.
- **Evidence.** Readiness barriers, invariant verification, panic/fail-closed
  posture, audit, and bounded rollback protect admitted transitions.
- **Difference.** Deterministic gates around stochastic cognition do not by
  themselves implement the canonical Simplex controller/fallback topology.
- **Maturity.** Bounded assurance: **CURRENT**; formal Simplex: **not claimed**.

## 8. Development and self-improvement

### Self-adaptive/autonomic systems, scaffold improvement, self-evolving agents, and AI4AI

- **Definition.** Self-adaptive systems alter behavior/configuration in response
  to observations; scaffold improvement changes model-facing orchestration;
  current “self-evolving agent” and AI4AI literature also covers systems using
  AI to improve agent software, prompts, tools, or models.
- **Classification.** **Direct technical fit** for bounded self-maintenance;
  **related architecture / intellectual lineage** for broad self-evolving-agent
  and AI4AI labels.
- **Evidence.** SentientOS can change system software, repository generation,
  maintenance authority/configuration generation, and resident process
  generation under exact custody. Memory and selected inference machinery have
  separate governed paths.
- **Difference.** Model weights are not autonomously improved; model output is
  not authority; repository mutation and adoption are bounded and distinct.
  “Self-improvement” must name the changed object.
- **Maturity.** Bounded system/scaffold evolution: **CURRENT / IMPLEMENTED BUT
  GOVERNED**.

### Recursive self-improvement and degree of loop closure

- **Definition.** Recursive self-improvement means improvements alter machinery
  that can participate in subsequent improvement cycles. “Degree of loop
  closure” usefully asks which observe–propose–implement–validate–adopt–resume
  stages are mechanical rather than assuming an all-or-nothing label.
- **Classification.** Bounded recurrence: **subsystem-level fit**; unrestricted
  RSI: **not currently justified**.
- **Evidence.** Automatic continuity, successor-generation adoption, governed
  repository absorption, exact resident replacement/readiness, and successor
  wake close the loop while the resident remains alive.
- **Difference.** Exact authority, operator posture, validation, scope, and
  fail-closed custody remain mandatory; death recovery and unrestricted change
  do not exist.
- **Maturity.** **CURRENT / IMPLEMENTED BUT BOUNDED**.

## 9. Runtime replacement and software evolution

### DSU, live update, process-image replacement, and runtime-generation adoption

- **Definition.** Dynamic software updating (DSU) commonly updates a running
  program without stopping it and may transform live code/state
  ([Hicks & Nettles, 2005](https://doi.org/10.1145/1075382.1075384)). Live
  upgrade/evolution is a broader family including coordinated replacement.
- **Classification.** Live software evolution: **related architecture /
  intellectual lineage**; governed process-image replacement: **direct technical
  fit**; classic in-place DSU: **not currently justified**.
- **Evidence.** Repository adoption leads to exact successor authority/config,
  predecessor quiescence, POSIX `sentientosd` `exec`, launch provenance,
  post-exec readiness, and successor wake.
- **Difference.** SentientOS replaces the process image and reconciles durable
  custody; it does not prove arbitrary hot code patching or general live-state
  transformation. Windows-native replacement is deferred.
- **Maturity.** POSIX resident adoption: **CURRENT / IMPLEMENTED BUT BOUNDED**.

## 10. Future neural coupling

### Passive BCI, neuroadaptive systems, and closed-loop BCI

- **Definition.** Passive BCI infers user state without voluntary control;
  neuroadaptive systems adapt from neural measures; closed-loop BCI couples
  sensing, interpretation, and feedback/action.
- **Classification.** **Research-horizon relationship**.
- **Evidence.** Only trajectory/intention material discusses dry-electrode,
  EEG, or neural coupling.
- **Difference.** No current production EEG/BCI acquisition, decoding, or
  closed-loop integration is proven.
- **Maturity.** **RESEARCH / TRAJECTORY**, not current capability.

## Terms intentionally rejected as current descriptions

The current repository does not justify claims of **active inference,
autopoiesis, Gödel machine, Theory of Mind, AGI, formal TMS, formal ATMS,
Simplex architecture, global formal reference monitor, global event sourcing,
classic DSU equivalence, personal knowledge graph, consciousness,
phenomenology, or demonstrated sentience**. Those terms require mechanisms or
empirical evidence stronger than broad architectural resemblance.
