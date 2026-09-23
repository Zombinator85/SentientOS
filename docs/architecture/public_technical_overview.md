# Public technical overview: current main

This document answers what exists and runs in current main. The [project thesis](sentientos_project_thesis.md) explains why; the [system atlas](current_repository_system_atlas.md) and [reviewer index](reviewer_release_readiness_index.md) retain exhaustive source and proof archaeology.

## Architecture and maturity vocabulary

Current deployment is **hosted SentientOS**: hardware -> Windows/Linux host kernel -> SentientOS services/runtime -> cognitive model(s). The repository also contains native paths and a literal **native SentientOS** architecture, but current main is not a mature general-purpose native OS and does not provide complete hardware support or general native resource enforcement.

Claims use separate predicates: implemented, callable, composed, resident, default-active, authorized, production-proven, and aspirational. One never implies the next.

## Resident surfaces

### Interactive cognition

`sentientos-chat` composes local-model catalog/custody, invocation admission, durable conversation sessions, history reconstruction, canonical memory retrieval, and explicit user-requested retention. Model availability still depends on cataloging, commissioning, activation, serving, and authority. Memory supplies provenance-bearing context; it is not current truth.

### World-State and host observation

`sentientosd` constructs evidence-bound World-State and performs read-only host-resource review. Sources retain provenance, freshness, staleness, and conflict. Current semantic cognitive projection is bounded and read-only. World-State is evidence, not an omniscient predictive model, and Phase 1 resource work does not write fan, PWM, or thermal controls.

More exactly, World-State is a deterministic, digest-bound, read-only projection with provenance, freshness, staleness, and conflicts; it is not perfect self-knowledge or philosophical omniscience. Phase-one host-resource operation is read-only. `host_resource_runtime.py` and its observation surfaces do not amount to universal computer control: **observation != blanket host control**.

### Bounded maintenance and succession

Maintenance has bounded resident parent supervision. The governed path can form evidence/work, implement, validate and correct, land a successor, configure transition, quiesce the predecessor, verify readiness, adopt, and perform POSIX process-image replacement. This is cooperative, bounded operational closure—not universal crash recovery, unrestricted RSI, or autonomous authority to modify anything.

**Current / implemented but bounded:** exact adoption may replace the resident POSIX `sentientosd` process image. `maintenance_resident_parent_supervision` is likewise implemented under bounded-orchestrator authority, while `real_service_restart` remains **BLOCKED / none**. Parent supervision does not promise universal recovery.

### Memory generations

Canonical governed conversation memory is live. Legacy memory managers and selective distillation machinery remain separately identifiable; selective-distillation and live-memory planning/readiness/interlocks do not silently become resident write authority. These generations must not be flattened into one maturity claim.

### Perception and external inference

Registry capabilities `perception_audio`, `perception_screen`, and `perception_vision` remain partial. `embodiment_ingress.py` and `host_resource_runtime.py` are real ingress/observation organs, not proof of closed embodiment.

External-model execution is implemented, not hypothetical: an exact HTTPS transport and execution-custody path exist. It remains unavailable by default, no provider is contacted automatically, and returned material remains `untrusted_external_data`. Implementation does not grant invocation, egress, disclosure, or adoption authority.

## Resident developmental writeback

The current developmental capability is `partial` with `bounded_state_transition` authority. Its resident temporal composition is:

```text
World-State evidence at tick N
-> bounded deterministic selection
-> governed developmental interpretation
-> typed digest-bound candidate
-> separate exact runtime admission
-> immutable developmental-history append
-> durable writeback receipt
-> retrieval at tick N+1+
-> read-only historical projection
-> bounded later cognition
```

Interpretation does not become truth; a candidate has no authority by itself; admission is not execution; durable storage does not prove learning; retrieval does not prove causation. Canonical explicit user-retention storage remains physically and semantically separate from developmental history.

## Current developmental experiments

### History intervention

A preregistered intervention holds current evidence and model constant while durable developmental history is present, withheld, and restored. It tests whether an output difference follows admitted history under the bounded projection path. It does not label the difference improvement.

### Same-frozen-state model replacement

A controlled experiment preserves frozen current evidence and developmental history while executing:

```text
model A + history
model A - history
model B + history
model B - history
model A + history restored
```

Exact operational model identity remains distinct from source-bound model-development/training provenance. Provenance claims do not become current fact, authority, or evidence of RSI.

### Repeated replication campaigns

The campaign instrument preregisters 2–32 fixed trial identities and binds immutable protocol, state, and report custody. It forbids silent retry and cherry-picking; reconstructs processes; verifies exact frozen context and repeated model/provenance; reports descriptive reproducibility; and preserves positive, negative, unstable, and interrupted outcomes.

This is repeated frozen-context evidence, not a production trial report unless actual production evidence is supplied and not a complete longitudinal developmental study. No current result establishes model-independent identity.

## Authority and consequence

The control plane separates capability definition, grant, policy, operational feasibility, admission, execution custody, attempted effect, result verification, durable receipt, and separately authorized adoption. Cognition may interpret or propose; it does not silently acquire effect authority.

capability definition != grant; grant != operational feasibility; operational feasibility != admission; admission != execution; proposal != authorization; repository absorption != runtime adoption.

Governance is also experimental instrumentation: it distinguishes observed evidence from interpretation, proposed work from authorized work, attempted effect from actual effect, validation from adoption, and landed source from running generation.

## Lineage custody

Current machinery can separately bind:

- persistent system and causal-history references;
- exact operational model identity/configuration;
- source-bound model-development/training provenance;
- predecessor/successor software and runtime generation.

These lineages answer different causal questions and are not interchangeable.

## Resources

Authenticated causal-resource principals establish identity, sponsorship, issuer provenance, and trusted public verification material. They answer whose work a resource-related event belongs to. They do **not** allocate CPU, GPU, RAM/VRAM, tokens, energy, thermal headroom, devices, or generalized task envelopes, and they confer no effect authority.

Host-resource observation is read-only. Semantic continuity toward scheduler/device assignment, measured consumption, consequence, and future allocation learning remains architectural work.

## Other implemented organs without false composition

Callable reflection/dream, goal-formation, self-narrative, perception, avatar, council/agent, cultural, federation, and historical components exist at varied maturity. Their existence does not establish a canonical resident dream life, mature endogenous priorities, closed embodiment, or a production social organism.

Federation can receive, rehearse, reject, adapt, compare, and disseminate provenance-bearing candidates under local authority. Candidate != doctrine; remote readiness != authority; receipt != adoption.

This is not a supported default production WAN synchronization deployment. SentientOS is not primarily a multi-agent orchestrator.

## Native and local compute boundary

The repository's native direction seeks to preserve principal, purpose, task lineage, authority, sponsorship, delegation, generation, evidence, effect, and consequence at lower enforcement layers. Current native paths do not fully enforce this semantic set.

Local cognition can use mature inference machinery. Native SentientOS does not require a bespoke tensor runtime: llama.cpp, PyTorch, CUDA, TensorRT, or a constrained Linux accelerator domain may implement mechanism while SentientOS retains constitutional and causal meaning. That delegation pattern is architecture, not current production GPU custody.

## Current truthful bottom line

Current main has real bounded resident developmental writeback and controlled history/model/replication instruments, plus bounded resident maintenance supervision and software succession. The complete developmental organism remains causally open. Production repeated evidence, a governed real resident A→B activation transition, general resource allocation/enforcement, and mature native operation remain future work.

SentientOS is not wholly formally verified. Its bounded authority/effect gates are reference-monitor-like, but the repository does not claim universal or complete mediation. Current succession is not unrestricted recursive self-improvement.
| Federation adaptation | Candidates, local variants, lineage and dissemination implemented | Forced convergence, remote authority, or production fleet |
| Resource principals | Causal identity/authentication/public trust implemented | Allocation, budget scalar, desire, or metabolism |

## Evidence navigation

Use these durable indexes rather than expanding this page into a proof warehouse:

- [Current repository system atlas](current_repository_system_atlas.md): exhaustive SHA-bound source, composition, persistence, and capability archaeology.
- [Reviewer release-readiness index](reviewer_release_readiness_index.md): historical proof wings and reviewer entry points.
- [Capability registry](../../sentientos/capability_registry.py): machine-readable status and forbidden implications.
- [Trajectory and materially incomplete causal bridges](sentientos_trajectory_and_missing_organs.md): composition, recovery, experimental, and product gaps.

This hierarchy preserves evidence history without making proof-wing enumeration the conceptual center of the architecture.

## Compact historical proof-path index

The workspace change-set admission surface is a **metadata-only eligibility gate before preflight**; lifecycle closure is a **metadata-only sealing layer**. Neither executes a change by existing.

The exhaustive indexes retain the explanation and status of these historical paths; this compact list preserves direct navigation without making phase chronology the conceptual architecture:

- `docs/architecture/reviewer_release_readiness_index.md`
- `docs/architecture/sentientos_trajectory_and_missing_organs.md`
- `docs/architecture/host_embodiment_substrate_phase1.md`
- `docs/architecture/host_embodiment_substrate_phase2_read_only_discovery.md`
- `docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md`
- `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`
- `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md`
- `docs/architecture/host_embodiment_execution_proof_wing.md`
- `docs/architecture/host_embodiment_authorization_review_wing.md`
- `docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md`
- `docs/architecture/host_embodiment_reviewer_demo_trace.md`
- `docs/architecture/reviewer_first_run_proof_bundle.md`
- `docs/architecture/host_actuation_safety_gate_wing.md`
- `docs/architecture/host_live_grant_readiness_wing.md`
- `docs/architecture/host_local_authorization_grant_wing.md`
- `docs/architecture/host_fulfillment_authorization_consumption_wing.md`
- `docs/architecture/host_fulfillment_executor_contract_wing.md`
- `docs/architecture/host_dry_run_execution_harness_wing.md`
- `docs/architecture/host_dry_run_audit_closure_wing.md`
- `docs/architecture/host_real_effect_capability_admission_wing.md`
- `docs/architecture/host_local_diagnostic_effect_pilot_wing.md`
- `docs/architecture/host_local_diagnostic_exact_rollback_pilot_wing.md`
- `docs/architecture/host_local_effect_transaction_ledger_wing.md`
- `docs/architecture/host_steward_delegated_runner_boundary_wing.md`
- `docs/architecture/host_builtin_local_effect_runner_pilot_wing.md`
- `docs/architecture/host_builtin_runner_transaction_orchestrator_wing.md`
- `docs/architecture/host_workspace_file_effect_pilot_wing.md`
- `docs/architecture/host_workspace_change_set_preflight_wing.md`
- `docs/architecture/host_workspace_change_set_execution_wing.md`
- `docs/architecture/host_workspace_change_set_execution_verification_wing.md`
- `docs/architecture/host_workspace_change_set_lifecycle_closure_wing.md`
- `docs/architecture/host_workspace_change_set_admission_wing.md`

- `docs/architecture/host_local_diagnostic_lifecycle_reviewer_guide.md`

## Bounded diagnostic execution lifecycle

The bounded local diagnostic execution, exact rollback, and lifecycle-closure path remains documented in `docs/architecture/host_local_diagnostic_lifecycle_reviewer_guide.md`; it does not broaden the developmental architecture or host authority.
