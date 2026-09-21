# SentientOS

**SentientOS is a persistent, model-agnostic runtime for agentic machine cognition, memory, perception, embodiment, and governed action.**

“Sentient” is an aspirational research direction, not a claim that this system is conscious or sentient today. The project asks what durable machine continuity, grounded self-observation, embodiment, development, and accountable action can support—and insists that the answer remain empirical.

## The model is not the system

An inference model is replaceable cognitive machinery inside SentientOS. The system also owns runtime and model-generation identity, durable conversation history, evidence, policy, capability custody, audit records, lifecycle state, and bounded effect paths. **Model identity is not system identity.** Model-agnostic means the architecture is not defined by one model or provider; it does not mean an arbitrary model can be swapped in without cataloging, commissioning, configuration, activation, serving, and admission.

Persistence is similarly domain-specific. Conversation records, atomic state, JSON/JSONL evidence, append-only or hash-linked ledgers, configuration/adoption artifacts, and repository history can survive a restart. Buffers, listeners, some deduplication windows, governor state, and caches remain process-local. Persistent does not mean every subsystem is crash-durable.

## What runs now

The `sentientosd` entrypoint runs a resident background loop for maintenance evidence, World-State construction, and read-only host-resource review. Configured maintenance owners can operate automatically, but consequential effects remain independently gated. `sentientos-chat` is the clearest supported local-model service path: installed model custody, activation, serving, per-generation inference admission, conversation identity, and canonical conversation retention are separate stages.

Implemented, bounded organs include:

- a deterministic control plane with capability definitions, grants, policy, admission, revocation, and domain-specific receipts;
- governed canonical conversation memory and exact session resumption;
- evidence-bound World-State projections with source lineage, freshness, staleness, and conflicts;
- read-only resident observation of CPU, memory, disk, services, and thermal evidence;
- local-model catalog, acquisition, commissioning, activation, serving, and inference machinery with explicit lifecycle boundaries;
- audio, screen, and vision adapters at differing partial activation and hardware maturity;
- bounded software-maintenance custody through evidence, work formation, implementation, validation/correction, landing, successor configuration, wake adoption, predecessor quiescence, and POSIX process-image replacement;
- exact external-model HTTPS execution custody, unavailable and inactive by default.

Council, agent, federation, cultural, and historical daemon libraries also exist. Their presence does not make them resident or default-composed. SentientOS is not primarily a multi-agent orchestrator.

## The reality boundary

Cognition may interpret, reason, and propose; it does not automatically possess authority. A representative effect chain is:

```text
capability definition
-> bounded grant
-> policy
-> operational feasibility
-> admission
-> execution custody
-> effect attempt
-> result verification
-> durable receipt
```

Domains vary, but no stage silently implies the next. In particular:

```text
state != authority
memory != current truth
proposal != authorization
capability definition != grant
grant != operational feasibility
operational feasibility != admission
admission != execution
execution != validation
validation != adoption
repository absorption != runtime adoption
```

World-State is a read-only evidence board, not omniscient truth or effect authority. Host observation is not blanket host control. Effectors exist for named domains, but most require separate operator, configuration, policy, and admission custody and are not resident defaults.

External-model invocation is a real bounded actuator: the repository implements registered authority, grant policy, feasibility checks, admission, endpoint/model and credential custody, request-material custody, exact HTTPS transport, response custody, and durable receipts. It is not resident-composed or generally enabled; no default provider grant, provider configuration, credential, or safe request-material source completes that live path. No provider is contacted automatically. Responses remain `untrusted_external_data` and are not automatically promoted into cognition, truth, memory, goals, or authority.

## Maturity and assurance

SentientOS has selected TLA+/formal models, executable checks, invariants, behavioral tests, audit machinery, and proof bundles. These formally model or executable-check named behaviors; they do **not** constitute machine-checked proof of the whole Python system. Reference-monitor-like and runtime-assurance-like properties apply only to named mediated domains, not universal mediation or whole-system formal RTA conformance.

The maintenance chain can adopt an exact validated successor and replace the resident POSIX `sentientosd` process image under bounded custody. This is real self-maintenance, not unrestricted recursive self-improvement. It depends on explicit configuration, authorities, validation, landing, adoption, successor readiness, and a live cooperative predecessor. Stable parent supervision and automatic recovery after unexpected resident death remain unimplemented. Generic service restart remains blocked.

Federation identity, trust epochs, replay protection, and WAN/lab evidence exist; a supported default production WAN synchronization deployment is not established. Synthetic tests prove code-path behavior, not deployed credentials, hardware, production accounts, default grants, resident composition, or an actual external effect.

## Install, run, and review

SentientOS requires Python 3.11 for the repository validation baseline.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .

python -m sentientos --help        # inspection and UI surface
python -m sentientos.ops --help    # operator/reviewer workflows
sentientosd                        # resident runtime
sentientos-chat                    # governed local chat service
```

Installation is not yet a one-click production deployment, and launch does not manufacture model artifacts, credentials, grants, or authority. See the [usage guide](docs/USAGE.md) for the supported entrypoint hierarchy.

## Read next

1. [One-page project statement](one_pager.md)
2. [Project thesis](docs/architecture/sentientos_project_thesis.md)
3. [Public technical overview](docs/architecture/public_technical_overview.md)
4. [Current repository system atlas](docs/architecture/current_repository_system_atlas.md) (exhaustive snapshot evidence)
5. [Reviewer release-readiness and proof](docs/architecture/reviewer_release_readiness_index.md)

Future gaps are tracked in the [trajectory and missing organs](docs/architecture/sentientos_trajectory_and_missing_organs.md). See also the [relationship to established terminology](docs/architecture/relationship_to_existing_terminology.md), [misconception filter](WHAT_SENTIENTOS_IS_NOT.md), [doctrine](DOCTRINE.md), and [semantic glossary](SEMANTIC_GLOSSARY.md).
