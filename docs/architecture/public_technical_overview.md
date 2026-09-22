# Public Technical Overview

## Purpose and claim discipline

This page is the current implementation anatomy and bounded capability map for SentientOS. The [project thesis](sentientos_project_thesis.md) explains the developmental research program; the [current repository system atlas](current_repository_system_atlas.md) and [reviewer release-readiness index](reviewer_release_readiness_index.md) retain exhaustive source/proof archaeology. Historical proof-wing phase names remain there rather than defining this overview.

SentientOS is a persistent, model-agnostic runtime and developmental causal substrate. Source existence, implementation, composition, enablement, automatic exercise, authority, effect capability, and production deployment are independent claims. “Sentient” is an empirical aspiration, not evidence of current consciousness, sentience, or personhood. The whole Python system is not formally verified.

## Composition at a glance

### Resident runtime

`sentientosd:main` installs signal-driven shutdown and runs resident maintenance evidence, World-State construction, and read-only host-resource review. Exact mutually exclusive configuration may add maintenance scheduler, wake, successor-generation, authority-continuity, and resident-adoption owners.

Importability is not residency. The cognitive cycle, inner-world orchestrator, dream loop, goal curator, councils, federation, cameras, avatars, and most effectors do not all start merely because `sentientosd` runs. Resident autonomous evidence and configured maintenance are real; this is neither zero autonomy nor universal autonomous composition.

### Local conversation and model path

`sentientos-chat` is the clearest supported cognitive service composition. Local models pass separately through catalog/acquisition, commissioning, activation, serving/loading, and per-generation inference admission. Explicit simulation is not silently mistaken for production inference. Automatic serving recovery, universal model discovery, hot switching, and provider fallback remain deferred.

**The model is not the system.** Models are replaceable cognitive machinery. System identity extends through durable history, evidence, configuration, authority, runtime/model lineage, and adopted software state. Model-agnostic means the architecture does not depend on one provider; it does not promise arbitrary swaps without compatibility, custody, and configuration.

## Developmental state and cognition

### Conversation history and canonical memory

`PersistentConversationService` reconstructs a bounded durable session history, retrieves a bounded canonical-memory snapshot, marks both as untrusted data rather than instructions, and supplies them to later inference. It then records the new turns. An explicitly requested user memory crosses a separate retention admission and canonical write boundary with source and operation binding.

Four generations must not be flattened:

1. **Canonical governed conversation memory is live.** Durable sessions, bounded reconstruction, explicit user-turn retention, canonical raw fragments, retrieval, and source-bound receipts are current paths.
2. **Legacy memory managers**, summaries, indexes, and goal stores remain available under older semantics.
3. **Selective distillation machinery** can describe retention, distillation, capsules, tomb intent, and review evidence. Tomb intent is not deletion, and this machinery is not a general formal truth-maintenance system.
4. **Live-memory planning/readiness/interlocks** verify later stages; not every such artifact is resident composition or a real canonical-root mutation.

Historical state can therefore affect later cognition. It is never automatically fact, policy, instruction, or authority: **memory != current truth**.

### Reflection, goals, identity, and self-narrative

The top-level `dream_loop.py` implements an idle reflection cycle over legacy memory. It selects high-importance or unfinished-goal material, produces and writes dream/reflection records, and can write reinforced-goal material. `goal_curator.py` discovers repeated-memory patterns and can create bounded background goals; it can also create a curiosity goal from a sufficiently novel perception. These are actual write paths in their legacy memory domain.

`IdentityManager` begins with an empty self-concept and offers event recording plus explicit key/value self-concept updates. `SelfNarrativeEngine`, called by `InnerWorldOrchestrator`, creates bounded chapters from cognitive reports using fixed experience-stability, ethical-signal, and metacognitive-activity axes.

These mechanisms are **implemented but callable/legacy/nonresident**, not a single default developmental loop. Their fixed categories are representational priors. Their existence does not prove endogenous identity, learning, self-awareness, or phenomenal experience.

### Evidence-bound self-state

World-State is a deterministic, digest-bound, read-only projection of source evidence. It carries provenance and lineage, freshness, staleness, conflicts, and source status. It does not resolve contradiction into truth, invoke a model, grant admission, mutate a repository, or authorize effects. It supports grounded self-description, not perfect self-knowledge or philosophical omniscience.

### Perception and embodiment

`perception_audio`, `perception_screen`, and `perception_vision` are registry-classified `partial` capabilities. `embodiment_ingress.py` admits bounded observations, and `host_resource_runtime.py` supplies resident host evidence. Avatar generation and pose machinery can produce visual/pose artifacts and logs. Household Presence supplies substantial camera policy and metadata custody while live capture remains deferred.

These are meaningful embodiment capabilities, but they do not amount to causally closed persistent embodied development. Hardware availability, calibration, privacy/consent closure, durable sensor lifecycle, action attribution, and learned sensorimotor consequence remain uneven or incomplete. Current world-state evidence is not a predictive world model.

## Authority and consequential effects

A representative modern path is:

```text
capability definition -> bounded grant -> policy -> operational feasibility
-> admission -> execution custody -> effect attempt
-> result verification -> durable receipt -> separate adoption where applicable
```

No earlier artifact silently establishes a later stage:

```text
state != authority
proposal != authorization
capability definition != grant
grant != operational feasibility
operational feasibility != admission
admission != execution
execution != validation
validation != adoption
repository absorption != runtime adoption
```

A receipt proves only the decision, custody step, attempt, result, or transition encoded by its domain schema. Model output does not create authority.

### Host observation and effects

Resident observation covers CPU, memory, disk, services, and thermal evidence. **Phase-one host-resource operation is read-only.** GUI, browser, filesystem, diagnostic, subprocess, service, and other effectors have domain-specific bounded implementations, but most require separate configuration, grants, admission, audit, and rollback or panic custody and are not resident defaults. They **do not amount to universal computer control**. Observation != blanket host control.

`real_service_restart` remains **BLOCKED / none**. Direct fan/PWM/thermal writes remain deferred. A capability definition, dry run, review packet, or executable class is not an active grant.

### External models

**External-model execution is implemented, not hypothetical.** Its bounded chain covers exact authority registration, grant policy, feasibility, runtime admission, endpoint/service/model and credential custody, request-material custody, exact HTTPS transport, response custody, and receipts.

It remains unavailable by default: no resident provider owner, default grant, provider configuration, credential, or safe request-material source completes the path. No provider is contacted automatically. Responses remain `untrusted_external_data` and gain no automatic status as cognition, truth, memory, goal, instruction, policy, or authority. Synthetic proof establishes code-path behavior, not a live account, credential, endpoint, default composition, or real external effect.

## Governed software recursion and runtime succession

The maintenance path can collect evidence, form bounded work, acquire scoped authority, invoke implementation, validate and correct, land or absorb exact repository state, configure successor authority, adopt on wake, quiesce a cooperative predecessor, verify successor readiness, and replace the resident POSIX `sentientosd` process image.

This is **CURRENT / IMPLEMENTED BUT BOUNDED** recursive software development/evolution. Governance determines which feedback-loop changes become authoritative; it does not make the recursion fictional. The path depends on exact configuration, custody, authority, validation, landing, adoption, readiness, and a cooperative live predecessor. It is **not unrestricted recursive self-improvement**, and a model does not own acceptance.

Parent supervision is **SCAFFOLDED / ELIGIBILITY-ONLY**. No stable parent runtime is implemented. No child watcher/restart loop supplies universal process-death recovery. Cooperative process-image replacement is not generic service supervision.

## Federation and local adaptation

Federation includes node identity, trust epochs, replay protection, and laboratory/WAN evidence. Improvement machinery additionally represents:

- provenance-preserving candidate production and reception;
- intake receipts and local custody/rehearsal runway;
- rejection and hold-for-adaptation outcomes;
- derived local variants;
- lineage comparison; and
- dissemination receipts that explicitly preserve non-adoption and no remote authority.

This architecture exchanges candidates, evidence, and context without requiring convergence: **candidate, not doctrine**. Local acceptance or adaptation remains locally governed. Metadata, readiness, rehearsal, dissemination, or a remote signature is not synchronization, merge, conflict resolution, adoption, consent, or execution authority.

A supported default production WAN synchronization deployment is **UNKNOWN / NOT ESTABLISHED**. Lab and synthetic proof are not fleet deployment. Agent and council libraries likewise exist without making SentientOS primarily a multi-agent orchestrator.

## Causal resource principals

Current causal-resource-principal code creates and verifies inert root identities bound to operator sponsorship, subject, epoch, lifetime, and issuer. Authentication binds an exact principal to an issuer provenance claim. Production Ed25519 verification is implemented against exact trusted public material loaded from an operator-provisioned, read-only catalog with time and revocation status. Production public trust custody is therefore real; issuer-provenance presence alone is still not trust.

A principal grants nothing, allocates nothing, and performs no effect. It answers causal ownership questions—whose work this is and under whose sponsorship—not “how much energy remains.” Provider spend, tool calls, proof passes, context, bandwidth, RAM, VRAM, disk, CPU, accelerators, deadlines, devices, thermal headroom, battery, and power remain distinct future allocation dimensions. This is a prerequisite for future homeostasis-like resource reasoning, not current allocation, appetite, or metabolism. Production private-key signer custody remains the next separately selected runtime slice.

## Assurance scope

Selected paths have TLA+/formal models, executable checks, invariants, audits, tests, and proof bundles. SentientOS is not wholly formally verified. Reference-monitor-like mediation and runtime-assurance-like contracts apply to named domains; the repository does not claim universal mediation, complete mediation, tamper-proof global enforcement, or whole-system formal RTA conformance.

The adversarial gradient-injection audit recognizes indirect contamination risks including memory-importance halos, approval traces becoming surrogate reward, expressive framing changing human selection, and long-horizon context priming. Recognition is not mitigation completeness.

## Capability maturity summary

| Area | Current status | What must not be inferred |
|---|---|---|
| Resident runtime | Maintenance evidence, World-State, read-only host review resident | All cognition/organs are resident |
| Local chat | Durable session context, admitted local inference and explicit retention composed | Memory is current truth or every model is interchangeable |
| Reflection/goals/self-narrative | Implemented and callable in older/inner-world paths | Canonical resident developmental closure |
| Perception/embodiment | Partial adapters and representations | Unified predictive world model or closed sensorimotor learning |
| Host effects | Named bounded effectors | Blanket host control or fan/PWM authority |
| External HTTPS | Exact bounded actuator implemented | Default egress, cognitive trust, or automatic provider call |
| Software succession | Validated adoption and POSIX replacement implemented | Unrestricted self-improvement or unexpected-death recovery |
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
