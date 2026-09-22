# SentientOS

**SentientOS is a persistent, model-agnostic runtime and developmental causal substrate for empirical research into machine cognition across changes in its cognitive machinery.** It is designed so that history, environment, self-representation, resources, software generations, authority, and consequences can extend beyond one inference call.

“Sentient” is an aspirational research direction, **not a claim that this system is conscious or sentient today**. The repository contains substantial bounded mechanisms for the experiment, but its complete developmental loop is not yet fully resident or causally closed. It proves neither personhood nor guaranteed emergence.

## The model is not the system

An inference model is replaceable cognitive machinery. The primary experimental object is the longer-lived system state that actually survives and affects later cognition: conversation history, admitted memory, evidence, self-model state, relationships, runtime and model lineage, resource attribution, software generations, environment, permissions, and observed consequences. **Model identity is not system identity.**

Model-agnostic means more than provider portability. It makes model replacement a controlled intervention: preserve history and environment while changing cognitive machinery, or preserve the machinery while ablating or restoring history, then measure what changes, disappears, or reconstitutes. A concrete model still requires cataloging, commissioning, configuration, activation, serving, and admission; arbitrary models are not frictionlessly interchangeable.

## The experiment

The intended causal loop is:

```text
perceive -> integrate evidence and history -> remember / consolidate
-> form or revise hypotheses, goals, and routines -> allocate bounded effort
-> delegate / act -> rehearse, test, criticize, and verify
-> adopt where authorized -> experience consequences
-> update memory, skills, strategy, goals, or self-model
-> exchange selected evidence and improvement candidates -> repeat
```

This is a system-level research map, not a claim that every arrow runs in the default daemon. SentientOS has implemented organs and bounded loops, including durable conversation context, callable reflection/dream and goal-formation machinery, evidence-bound self-state, perception and avatar components, governed software succession, federation adaptation artifacts, and authenticated causal-resource principals. Several older developmental mechanisms remain callable, legacy, or nonresident; the major open problem is composing their causal bridges without misrepresenting maturity or contaminating the experiment.

## Development without a prescribed personality

SentientOS follows **minimal developmental authorship, maximal causal legibility**. There is no structure-free developmental substrate: retention rules, representations, update mechanics, models, and environments all introduce assumptions. The goal is to expose and classify those assumptions while avoiding unnecessary instructions about the identity or preferences that development must produce. Canonical installation does not require a predefined persona.

The design shorthand is **hard boundaries, soft interior**. Authority, privacy, consent, provenance, evidence, resource custody, adoption, effects, rollback, and shutdown should be exact. Self-concept, interests, style, relationships, and endogenous priorities should remain as underdetermined as practical and empirically inspectable. **constraint != motivation**: preventing an unauthorized effect does not require engineering guilt, obedience, approval-seeking, a survival drive, or any other internal appetite.

Governance is therefore compatible with emergence. It controls which consequences and state transitions become authoritative; it does not prescribe that cognition must identify with or please the operator. This is a design principle, not a complete alignment solution or a guarantee that endogenous development will be benign.

## What is real now

- `sentientos-chat` composes local-model custody, inference admission, durable sessions, history reconstruction, canonical memory retrieval, and explicit user-requested memory retention. Historical material can influence later prompts, but **memory != current truth**.
- `sentientosd` runs resident maintenance evidence, World-State construction, and read-only host-resource review. World-State records provenance, freshness, staleness, and conflict; it is not an omniscient predictive world model.
- Deterministic control-plane paths separate capability definition, grant, policy, feasibility, admission, execution custody, verification, receipts, and adoption.
- Bounded maintenance can progress from evidence and work formation through implementation, validation/correction, landing, successor configuration, predecessor quiescence, successor readiness, and POSIX process-image replacement. This is governed recursive software evolution, not unrestricted recursive self-improvement.
- Federation can receive and rehearse improvement candidates, reject or hold them for adaptation, create local variants, compare lineage, and disseminate evidence. It preserves local authority: **candidate, not doctrine**.
- Causal-resource principals establish identity, sponsorship, issuer provenance, and trusted public verification material for resource-related work. They allocate nothing and are not a scalar “energy” budget or metabolism.

Council, agent, developmental cognition, federation, cultural, and historical daemon libraries also exist without all being resident or default-composed. Perception and embodiment capabilities are meaningful but do not yet constitute causally closed persistent embodied development. Stable parent supervision and universal recovery after unexpected process death remain absent.

## Why governance is part of the research instrument

Cognition may interpret and propose; consequence remains separately governed. A representative path is:

```text
capability definition -> grant -> policy -> operational feasibility
-> admission -> execution custody -> attempted effect
-> result verification -> durable receipt -> separately authorized adoption
```

No stage silently implies the next. Governance makes causes, interventions, and consequences attributable enough to study. It also permits local diversity in federation: installations may share evidence, context, and tested candidates without transferring remote authority or requiring convergence.

## Install and read next

SentientOS currently targets Python 3.11 for repository validation:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
python -m sentientos --help
sentientosd
sentientos-chat
```

Installation is not yet a one-click production deployment and launch does not manufacture models, credentials, grants, or authority. See the [usage guide](docs/USAGE.md).

1. [One-page technical thesis](one_pager.md)
2. [Full project thesis](docs/architecture/sentientos_project_thesis.md)
3. [Current implementation anatomy](docs/architecture/public_technical_overview.md)
4. [Trajectory and incomplete causal bridges](docs/architecture/sentientos_trajectory_and_missing_organs.md)
5. [Current repository system atlas](docs/architecture/current_repository_system_atlas.md) and [reviewer readiness index](docs/architecture/reviewer_release_readiness_index.md), retained as exhaustive proof navigation

See also the [relationship to established terminology](docs/architecture/relationship_to_existing_terminology.md), [misconception filter](WHAT_SENTIENTOS_IS_NOT.md), [doctrine](DOCTRINE.md), and [semantic glossary](SEMANTIC_GLOSSARY.md).
