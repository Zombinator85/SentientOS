# SentientOS system orientation

This is a source-oriented starting point for contributors joining the repository
without prior conversation context. It complements the project thesis and public
technical overview with a compact map of the system's major owners and the
evidence needed to describe their maturity. It is not a capability census or a
claim that every optional path is active on a particular host.

**Source point:** published `main` was inspected at `b1eeac34c04a2fcb9cdfdccb8891456e90831e28`
(the merge of cognition PR #3628). The resource-governance work described below
is in the working branch for open, unmerged [PR #3629](https://github.com/Zombinator85/SentientOS/pull/3629).
The branch's earlier checkpoint was `7beb7e28fea8b15a5368d431d95b5764b203f4f4`;
this page and the next code increment are newer working-tree changes. Check the
PR head and current source before relying on this dated work note.

## What the system is

SentientOS is a hosted operating environment under active development, with a
native lower-layer operating-system implementation as a longer-term objective.
The hosted system delegates kernel, device, process, and inference-runtime work
to Windows or Linux while composing persistent state, governance, resource
semantics, model lifecycle, maintenance, cognition, and other services above
them. It is already software, not only a proposal; it is not currently a mature
general-purpose bare-metal replacement for Windows or Linux.

The persistent system and its causal organization are the object being developed.
Cognitive models are replaceable components. Exact model identity, model
development provenance, SentientOS software generation, persistent state,
authority, and observed consequences are distinct lineages. A stored record,
model replacement, or changed output alone does not establish continuity,
learning, or improvement.

The architecture aims to preserve this chain:

```text
environment and subsystem evidence -> World-State and bounded cognition
-> interpretation / proposal -> sponsorship and authority
-> owner-controlled effect -> independent observation and attribution
-> separately admitted durable change -> later cognition or conduct
```

## Major runtime organs and owners

| Organ | Main source entry points | What it owns and what remains bounded |
| --- | --- | --- |
| Hosted daemon and composition | [`sentientosd.py`](../../sentientosd.py), [`sentientos/runtime/`](../../sentientos/runtime/) | Composes configured owners and lifecycle. Configuration and composition do not imply default activation or production evidence. |
| Control plane and governance | [`sentientos/control_plane_kernel.py`](../../sentientos/control_plane_kernel.py), [`sentientos/runtime_governor.py`](../../sentientos/runtime_governor.py) | Admits typed, scoped actions and delegates policy. Evidence and proposals do not grant authority. |
| World-State and observation | [`sentientos/host_resource_runtime.py`](../../sentientos/host_resource_runtime.py), [`sentientos/world_state_board.py`](../../sentientos/world_state_board.py), [`sentientos/world_state_sources.py`](../../sentientos/world_state_sources.py) | Produces provenance- and freshness-bound observations. Host-resource phase one is read-only; telemetry is not hardware-control authority. |
| Cognition and persistent memory | [`sentientos/resident_developmental_cognition.py`](../../sentientos/resident_developmental_cognition.py), [`sentientos/resident_developmental_writeback.py`](../../sentientos/resident_developmental_writeback.py), [`sentientos/persistent_epistemic_state.py`](../../sentientos/persistent_epistemic_state.py) | Consumes bounded current evidence and eligible prior state; durable mutations have separate owners and admission. The cognition PR #3628 is merged; its deterministic planning result is mechanism evidence, not a live-model benefit claim. |
| Model lifecycle and chat | [`sentientos/local_model_production_commissioning.py`](../../sentientos/local_model_production_commissioning.py), [`sentientos/local_model_production_activation.py`](../../sentientos/local_model_production_activation.py), [`sentientos/local_model_production_serving.py`](../../sentientos/local_model_production_serving.py), [`sentientos/local_model_serving_inference.py`](../../sentientos/local_model_serving_inference.py) | Acquisition, commissioning, activation, serving, and inference are separate stages and authorities. Production chat's automatic recovery/re-establishment and hot switching remain deferred. |
| Forge and software maintenance | [`sentientos/forge_daemon.py`](../../sentientos/forge_daemon.py), [`sentientos/maintenance_autonomy_cycle.py`](../../sentientos/maintenance_autonomy_cycle.py), [`sentientos/maintenance_validation_controller.py`](../../sentientos/maintenance_validation_controller.py) | Implements bounded development, validation, and publication paths with separate gates. This is not unrestricted recursive self-improvement or blanket repository authority. |
| Software succession | [`sentientos/maintenance_resident_runtime_adoption.py`](../../sentientos/maintenance_resident_runtime_adoption.py), [`sentientos/maintenance_resident_parent_supervision.py`](../../sentientos/maintenance_resident_parent_supervision.py) | Has a bounded POSIX process-image replacement path with provenance, quiescence, transition, and readiness checks. This differs from model serving and model transition. |
| Federation | [`sentientos/federation/`](../../sentientos/federation/) | Includes peer identity, authentication, replay, trust, drift, and improvement-intake owners. Mechanisms in source do not establish an operating production network of independent peers. |
| Embodiment and gaming observation | [`sentientos/embodiment_ingress.py`](../../sentientos/embodiment_ingress.py), [`sentientos/gaming_companion_edge_runtime.py`](../../sentientos/gaming_companion_edge_runtime.py), [`sentientos/game_performance_bridge.py`](../../sentientos/game_performance_bridge.py) | Composes bounded observations and explicitly mediated effects. Windows game performance sampling is read-only and limited to configured process allowlists. |
| Capability vocabulary and native direction | [`sentientos/capability_registry.py`](../../sentientos/capability_registry.py), [native exploratory-pilot records](../development/native_codex_unverified_exploratory_pilot.md) | Declares implemented, partial, blocked, deferred, and scaffolded surfaces. Registry entries describe mechanisms and boundaries; they do not prove operation. Native work remains exploratory and is not a complete general-purpose OS kernel. |

These are owner groupings, not a claim that every subsystem runs in the default
daemon. For current wiring, inspect `sentientosd.py` and the relevant runtime
startup path; for exact boundaries, read the owner and its tests. The
[capability registry](../../sentientos/capability_registry.py) and
[source-bound atlas index](system_atlas_index.md) complement source inspection.
The selected atlas is an immutable historical snapshot, not a current census.

## Current resource-governance work

The open resource increment in PR #3629 connects both host and game observations
to optional local-inference admission:

```text
bounded host-resource collectors + allowlisted Windows game observation
-> shared serving ControlPlaneKernel / RuntimeGovernor evidence
-> signed authenticated game bridge + verified foreground receiver
-> governed inference admission and receipt
```

At the PR's source point, the production Windows edge can publish read-only
game-performance samples when explicitly configured with an allowlist. The
production chat composition now invokes the existing bounded read-only
`HostResourceRuntimeCoordinator` with the same kernel used by serving admission.
It uses a short CPU, memory, and NVIDIA GPU collector plan before inference and
binds a bounded resource-evidence summary into the request receipt. Current
verified frame-pressure evidence defers optional inference; current host
pressure gains game-priority meaning only while verified game evidence is fresh.
Enforcement depends on the configured `RuntimeGovernor` posture; advisory mode
records the decision but does not defer. The deterministic production-serving
fixture drives a synthetic host reading and signed game sample through the real
coordinator and invocation owner. It verifies no model call, a deferred
invocation receipt, persisted host and game evidence references, and preservation
of the active serving lifetime. This is composed software behavior, not a
measured hardware benefit.

Production release is a separate unresolved lifecycle problem. The production
serving controller owns an exact model process; invalidating serving unloads it
and ends that lifetime. The current production chat capability defers automatic
serving recovery or re-establishment, while an existing recovery controller
consumes a separately approved request. The Ollama development invoker has a
governed residency-release path, but that is not the production llama.cpp
serving owner. Do not conflate deferred future inference with reclaimed GPU
memory, or add automatic unload/restart without preserving model-serving,
quiescence, receipt, custody, and recovery contracts.

The intended priority is gaming workloads before optional inference. Existing
game and host telemetry support inference admission only; they grant no authority over
the host scheduler, GPU allocation, fans, power profiles, or game processes.
The next implementation increment should continue the causal chain through
existing resource and serving owners, with deterministic fixture behavior
clearly separated from hardware observation.

## Reading and claim discipline

Use these predicates precisely:

- **Implemented:** a bounded mechanism exists in source.
- **Composed:** a real owner-to-owner runtime path connects those mechanisms.
- **Production-evidenced:** a qualifying nonsynthetic execution or observation
  occurred and was attributed.
- **Projected:** a connection or outcome remains intended, incomplete, or
  empirically unestablished.

Also distinguish configured, default-active, authorized, effectful, and
measured. A passing deterministic test can establish a software contract or
composed fixture path. It does not by itself establish runtime activation,
hardware impact, real-world improvement, learning, identity, or consciousness.

For a cold start, read the [README](../../README.md), this page, the
[public technical overview](public_technical_overview.md), the [project
thesis](sentientos_project_thesis.md), then the relevant source, owner contracts,
tests, and fresh execution evidence. The [whole-system maturity
report](whole_system_maturity_report.md) and [trajectory and missing
organs](sentientos_trajectory_and_missing_organs.md) provide broader lifecycle
analysis, but check their source dates before treating them as current status.
