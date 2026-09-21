# Forward Documentation Reconciliation Docket

> This is an evidence/action docket, **not replacement public documentation**. No target document listed here was edited by this task. Findings bind to the current repository atlas and should be rechecked at rewrite time.

## Priority convention

High means a claim risks confusing implementation with authority, default activation, production composition, or whole-system assurance. Medium means an important maturity qualifier or reorganization is missing.

## `README.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| persistent | supported_but_missing_important_qualifier | Persistence is domain-specific; some state is process-only. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Persistence is domain-specific; some state is process-only. | maturity clarification |
| model-agnostic | supported_but_missing_important_qualifier | System identity is separable, but current local serving is explicitly commissioned. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | System identity is separable, but current local serving is explicitly commissioned. | maturity clarification |
| autonomous | supported_but_missing_important_qualifier | Resident loop exists; consequential paths remain gated. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Resident loop exists; consequential paths remain gated. | maturity clarification |
| governed action | supported | Control-plane and custody paths exist. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Control-plane and custody paths exist. | maturity clarification |
| crash resilient | supported_but_missing_important_qualifier | Some durable recovery exists; universal unexpected-death recovery does not. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Some durable recovery exists; universal unexpected-death recovery does not. | maturity clarification |
| distributed | supported_but_missing_important_qualifier | Federation surfaces exist, but live default WAN sync is not established. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Federation surfaces exist, but live default WAN sync is not established. | maturity clarification |
| multi-agent | supported_but_missing_important_qualifier | Council/agent libraries exist without resident default orchestration. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Council/agent libraries exist without resident default orchestration. | maturity clarification |
| formally verified | contradicted_by_current_source | TLA+ specs do not establish whole-system formal verification. Evidence: sentientosd.py, sentientos/capability_registry.py | high | TLA+ specs do not establish whole-system formal verification. | maturity clarification |
| live memory | supported_but_missing_important_qualifier | Canonical chat memory is live; other memory stages are metadata-only or legacy. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Canonical chat memory is live; other memory stages are metadata-only or legacy. | maturity clarification |
| reference-monitor-like | ambiguous | Control-plane mediation is bounded by composed paths, not a universal reference monitor. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Control-plane mediation is bounded by composed paths, not a universal reference monitor. | maturity clarification |
| runtime-assurance-like | supported_but_missing_important_qualifier | Assurance contracts cover named domains only. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Assurance contracts cover named domains only. | maturity clarification |

## `one_pager.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| self-maintaining | supported_but_missing_important_qualifier | Maintenance requires configuration and independent landing/adoption. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Maintenance requires configuration and independent landing/adoption. | maturity clarification |
| self-modifying | supported_but_missing_important_qualifier | Repository mutation exists through governed workcell, not direct recursive mutation. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Repository mutation exists through governed workcell, not direct recursive mutation. | maturity clarification |
| recursive self-improvement | contradicted_by_current_source | Maintenance is bounded, gated, and externally landed/adopted. Evidence: sentientosd.py, sentientos/capability_registry.py | high | Maintenance is bounded, gated, and externally landed/adopted. | maturity clarification |
| network capable | supported_but_missing_important_qualifier | Specific gated transports exist; none imply default egress. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Specific gated transports exist; none imply default egress. | maturity clarification |

## `docs/architecture/public_technical_overview.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| model-independent identity | supported | Runtime and model generation identity are separated. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Runtime and model generation identity are separated. | maturity clarification |
| host control | supported_but_missing_important_qualifier | Read-only observation is resident; real effects are separately admitted and not default. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Read-only observation is resident; real effects are separately admitted and not default. | maturity clarification |
| external-model capable | supported_but_missing_important_qualifier | Transport/custody implemented, unavailable by default. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Transport/custody implemented, unavailable by default. | maturity clarification |
| perception-capable | supported_but_missing_important_qualifier | Adapters differ in hardware, provenance, and activation maturity. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Adapters differ in hardware, provenance, and activation maturity. | maturity clarification |
| world-state aware | supported_but_missing_important_qualifier | Evidence board includes conflicts/freshness and is not authoritative truth. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Evidence board includes conflicts/freshness and is not authoritative truth. | maturity clarification |

## `docs/architecture/sentientos_project_thesis.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| introspective | supported_but_missing_important_qualifier | World-State is evidence projection, not omniscient truth. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | World-State is evidence projection, not omniscient truth. | maturity clarification |
| embodied | supported_but_missing_important_qualifier | Many embodiment chains are telemetry/policy/review only. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Many embodiment chains are telemetry/policy/review only. | maturity clarification |
| sentient | ambiguous | Project name/thesis is not implementation evidence of sentience. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Project name/thesis is not implementation evidence of sentience. | maturity clarification |

## `docs/architecture/sentientos_trajectory_and_missing_organs.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| missing organs | stale | Some named gaps now have bounded implementations; re-evaluate line by line. Evidence: sentientosd.py, sentientos/capability_registry.py | high | Some named gaps now have bounded implementations; re-evaluate line by line. | maturity clarification |

## `WHAT_SENTIENTOS_IS_NOT.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| not conscious | supported | No implementation proof of consciousness. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | No implementation proof of consciousness. | maturity clarification |
| not provider authority | supported | External-model implementation does not create default provider authority. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | External-model implementation does not create default provider authority. | maturity clarification |

## `DOCTRINE.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| operator authority | supported | Privileged effects fail closed behind operator/control boundaries. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Privileged effects fail closed behind operator/control boundaries. | maturity clarification |
| safe shutdown | supported | Resident loop installs signal-driven shutdown and owner stop paths. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Resident loop installs signal-driven shutdown and owner stop paths. | maturity clarification |

## `SEMANTIC_GLOSSARY.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| receipt | supported_but_missing_important_qualifier | Receipt meaning remains domain-specific and does not itself prove effect. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Receipt meaning remains domain-specific and does not itself prove effect. | maturity clarification |
| authority | supported | Definitions, grants, admission, custody and adoption are distinct. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Definitions, grants, admission, custody and adoption are distinct. | maturity clarification |

## `docs/USAGE.md`

| Claim/section | Classification | Actual repository posture / evidence | Priority | Direction | Change type |
|---|---|---|---|---|---|
| supported commands | ambiguous | Packaged scripts exceed the prominently documented launch set. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Packaged scripts exceed the prominently documented launch set. | maturity clarification |
| GUI/dashboard | historical_language_in_current_doc | Several shipped interfaces are compatibility or manual launch surfaces. Evidence: sentientosd.py, sentientos/capability_registry.py | medium | Several shipped interfaces are compatibility or manual launch surfaces. | maturity clarification |

## Deep material to promote in the later rewrite

* Promote the definition → grant → feasibility → admission → execution custody → result/validation → receipt → adoption distinction from the control-plane and effect-custody documents.
* Promote the local-model lifecycle distinction among catalog, acquisition, commissioning, activation, serving, and per-generation inference admission.
* Promote World-State conflict/freshness semantics and its non-authoritative evidence-board posture.
* Promote the separation between resident host observation and non-default real-effect fulfillment.
* Promote maintenance handoff versus merge/adoption/process replacement, including configuration and operator boundaries.
* Promote explicit synthetic/test versus production composition language.

## Material currently over-prominent

Cultural cathedral/ritual/avatar and early council/daemon descriptions can remain part of project history and compatibility guidance, but should not lead the explanation of the current authority architecture. “Autonomous,” “self-maintaining,” “distributed,” and “formally verified” need bounded qualifiers wherever filenames, historical ambitions, or isolated tests currently carry more rhetorical weight than current composition.

## Rewrite constraints for the next task

Do not turn a receipt into effect proof, readiness into authority, a registry row into composition, a test fake into deployment, or a resident import into automatic exercise. Preserve unknowns and domain-specific limitations. Re-run source and registry checks before replacement prose because this docket is SHA-bound.
