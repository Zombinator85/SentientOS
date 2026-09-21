# Public Technical Overview

## Scope and claim discipline

SentientOS is a persistent, model-agnostic runtime for agentic machine cognition, memory, perception, embodiment, and governed action. This page describes current repository reality. Source code, runtime composition, activation, authority, effect capability, default behavior, and production maturity are independent claims.

“Sentient” is an empirical research aspiration, not evidence of consciousness or demonstrated sentience. “OS” describes the intended semantic scope around cognition; the current system is a hosted Python environment, not a mature bare-metal kernel.

The exhaustive, SHA-bound evidence is the [current repository system atlas](current_repository_system_atlas.md). The [terminology bridge](relationship_to_existing_terminology.md) maps carefully scoped comparisons to established literature.

## Current system anatomy

### Resident runtime

`sentientosd:main` installs signal-driven shutdown and runs a persistent SentientOS environment. Its loop composes maintenance evidence, World-State material, and read-only host-resource review. Exact, mutually exclusive configuration can add maintenance scheduler, wake, authority-continuity, successor-generation, and runtime-adoption owners. Importability alone does not make a subsystem resident: the cognitive cycle, councils, historical daemons, federation, cameras, and effectors do not all start with `sentientosd`.

Resident autonomous maintenance/evidence machinery exists, while consequential effects remain explicitly gated. This is neither zero autonomy nor complete autonomy.

### The model is not the system

SentientOS is not identical to its currently active inference model. Models are replaceable cognitive machinery within a longer-lived system identity.

```text
System lifecycle: identity + memory + evidence + policy + authority + runtime generations
Inference lifecycle: catalog -> acquisition -> commissioning -> activation
                     -> serving/loading -> per-generation inference admission
```

Each local-model stage has separate records and constraints; an earlier stage never silently grants a later one. `sentientos-chat` is the clearest current service composition, with explicit simulation rather than fallback. Automatic serving recovery, hot activation switching, universal model discovery, and provider fallback remain deferred.

Model-agnostic means the system architecture and identity do not depend on one model/provider. It does not mean every model works without acquisition, compatibility checks, commissioning, activation, and configuration.

### Memory and continuity

Four generations must not be flattened:

1. **Canonical governed conversation memory is live.** Explicit user-turn retention, bounded retrieval, durable raw fragments, exact session resume, and source-bound receipts are real mutation and retrieval paths.
2. **Legacy memory managers, summaries, and indexes** remain available with historical semantics.
3. **Selective distillation machinery** can retain, distill, capsule, create tomb intent, and produce review evidence. Tomb intent is not deletion; its contract is metadata-verification-only and not a formal Truth Maintenance System.
4. **Live-memory planning/readiness/interlocks** describe and verify later commit stages; not every selective-memory stage is resident-composed or live-writing.

Memory may influence cognition, but recalled material is not automatically current fact, policy, instruction, or authority. Persistence is domain-specific: durable JSON/JSONL, atomic state, ledgers, repository history, and configuration coexist with process-local buffers, listeners, caches, dedupe windows, and some governor state.

### Evidence-bound introspection and self-state

World-State is a deterministic, digest-bound, read-only projection of source evidence. It carries provenance and lineage, freshness/staleness, conflicts, and source status. It does not resolve contradictory claims into truth, invoke a model, mutate a repository, grant admission, or authorize effects. It supports grounded self-description, not perfect self-knowledge or philosophical omniscience.

### Perception and embodiment

`perception_audio`, `perception_screen`, and `perception_vision` are registry-classified `partial` capabilities. Their adapters differ in hardware dependence, provenance, and activation maturity. `embodiment_ingress.py` admits bounded observations; `host_resource_runtime.py` supplies resident host evidence. Household Presence camera work has **CURRENT / IMPLEMENTED POLICY AND METADATA CUSTODY; LIVE CAPTURE DEFERRED**: policy, future-live deferral, and dry-run continuation gates exist, but those artifacts are not live capture.

This supports an embodied research program without claiming every sensor is installed, present, or resident.

## Authority and effects

### Modern decomposition

A representative current chain is:

```text
capability definition -> bounded grant -> policy -> operational feasibility
-> admission -> execution custody -> effect attempt -> result verification
-> durable receipt
```

Not every domain instantiates every stage identically. The invariant is non-collapse:

- capability definition does not grant;
- grant does not prove operational feasibility;
- operational feasibility does not admit;
- admission is not execution;
- execution is not validation;
- validation is not adoption;
- repository absorption != runtime adoption;
- model output does not grant authority.

A receipt is domain-specific. It proves the recorded decision, attempt, result, or transition—not automatically that an intended real-world effect happened.

### Host observation and host effects

Resident observation covers CPU, memory, disk, service, and thermal evidence. Phase-one host-resource operation is read-only. GUI and browser host interaction implementations are bounded and do not amount to universal computer control. Filesystem, diagnostic, subprocess, service, GUI, and other actuator classes exist, but most require separate grants, operator/configuration custody, admission, rollback or audit paths and are not resident defaults. Observation != blanket host control.

`real_service_restart` remains **BLOCKED / none**. A registry entry or executable class is not a runtime grant.

### External-model execution

External-model execution is implemented, not hypothetical. The path includes:

- registered authority and exact effect definition;
- runtime grant policy;
- operational-feasibility checks;
- runtime admission;
- endpoint, service, model, and credential custody;
- exact request-material custody;
- exact HTTPS transport;
- bounded result and receipt custody.

It is nevertheless unavailable by default: it is not resident-composed, and there is no default runtime provider grant, provider configuration, credential, or safe default request-material source completing a live route. No provider is contacted automatically. Response material remains `untrusted_external_data`; it is not automatically promoted into cognition, truth, memory, goals, policy, or authority.

Synthetic transport and credential tests prove exact code-path behavior. They do not prove a deployed account, live credential, production endpoint, resident composition, default grant, or actual external call.

## Maintenance and runtime generations

The current maintenance path can collect resident evidence, form bounded work, obtain scoped authority, invoke admitted implementation, validate and correct, land or absorb exact repository state, prepare successor authority/configuration, adopt on wake, quiesce a cooperative predecessor, prove an independently ready successor, and replace the resident POSIX `sentientosd` process image.

This is **CURRENT / IMPLEMENTED BUT BOUNDED** software evolution. It depends on exact configuration, custody, authorities, validation, landing, adoption, readiness, and predecessor continuity. It is not unrestricted recursive self-improvement, and a model does not own acceptance or authority.

Parent supervision is **SCAFFOLDED / ELIGIBILITY-ONLY**. No stable parent runtime is implemented. No child watcher/restart loop provides process-death recovery. Unexpected resident death therefore lacks universal automatic recovery; the implemented process-image replacement is a cooperative transition, not generic service management.

## Federation, agents, and assurance

Federation modules include identities, trust epochs, replay protection, transport-related code, and WAN/lab evidence. A supported, default production WAN synchronization deployment is **UNKNOWN / NOT ESTABLISHED**. Federation evidence or readiness is not adoption, consent, synchronization, or transport authority.

Agent, council, orchestration, dream, reflex, and historical daemon libraries exist. They may be explicitly invoked and tested, but are not default resident composition. SentientOS is therefore not best described as a default multi-agent orchestrator.

Selected behaviors and invariants have TLA+/formal models, executable verification, tests, audits, and proof machinery. SentientOS is not wholly formally verified. Reference-monitor-like mediation and runtime-assurance-like contracts are scoped to named paths; the repository does not claim complete mediation, tamper-proof global enforcement, or whole-system formal RTA conformance.

Wi-Fi/RF sensing, including live Wi-Fi/CSI/RF environmental sensing or imaging, remains deferred or blocked and is **RESEARCH / TRAJECTORY**, not a current capability.

## Current limits and research trajectory

Material gaps include one-click installation and platform service integration; stable parent supervision and process-death recovery; production-default external inference composition; broader sensor/hardware availability and actuation integration; general memory truth-maintenance; supported production WAN federation; and longer controlled continuity experiments across model and runtime generations.

These gaps coexist with strong implemented boundaries. Effect-capable does not mean default-active. Synthetic proof does not mean production composition. Cultural compatibility naming—such as cathedral, ritual, blessing, or avatar—does not define the modern control architecture.

See the [project thesis](sentientos_project_thesis.md) for why this machine is being built and [trajectory](sentientos_trajectory_and_missing_organs.md) for what remains incomplete.

## Proof catalogue

Use these paths to inspect claims rather than relying on this narrative alone:

| Question | Primary source | Behavioral proof / ledger |
|---|---|---|
| What is resident? | `sentientosd.py` | `tests/test_sentientosd_runtime_closure.py` |
| What capability status is canonical? | `sentientos/capability_registry.py` | `tests/test_capability_registry.py` |
| How is local inference separated? | `sentientos/local_model_*`, `sentientos/chat_service.py` | local-model commissioning, activation, serving, and chat tests |
| What conversation memory is live? | `sentientos/canonical_memory.py`, `sentientos/conversation_session.py` | `tests/test_persistent_governed_conversation.py` |
| What is World-State? | `sentientos/world_state_board.py`, `sentientos/world_state_sources.py` | `tests/test_world_state_board.py` |
| How are external calls held? | `sentientos/external_model_execution_custody.py`, `sentientos/external_model_https_transport.py` | external-model authority, feasibility, admission, and custody tests |
| How can a successor run? | `sentientos/maintenance_resident_runtime_adoption.py` | resident-adoption and successor-generation tests |
| What does the repository-wide evidence say? | `architecture/current_repository_system_atlas.json` | [narrative atlas](current_repository_system_atlas.md) |
| What is release-ready? | [reviewer release-readiness index](reviewer_release_readiness_index.md) | proof bundles and matrices linked there |

## Appendix: detailed proof and reviewer catalogue

The following preserved catalogue is navigation for reviewers. It does not expand the present-tense claims above; each linked wing retains its own scoped authority and maturity boundary.
## Proof map (commands and tests)

Run from repository root:

```bash
# Control-plane and runtime hardening
python -m scripts.run_tests -q tests/test_control_plane_kernel.py
python -m scripts.run_tests -q tests/test_sentientosd_runtime_closure.py

# Federation trust ledger recovery and probe ordering
python -m scripts.run_tests -q tests/test_trust_ledger.py sentientos/tests/test_trust_ledger_recovery.py

# Hardened production model/runtime and explicit recovery
python -m scripts.run_tests -q tests/test_local_model_production_commissioning.py tests/test_local_model_production_commissioning_authority.py tests/test_local_model_production_commissioning_capability_admission.py tests/test_local_model_production_activation.py tests/test_local_model_production_activation_capability_admission.py tests/test_local_model_production_serving.py tests/test_local_model_serving_inference.py tests/test_chat_service_hardened_serving.py tests/test_local_model_chat_runtime_startup.py tests/test_local_model_chat_recovery.py tests/test_local_model_chat_recovery_capability_admission.py

# Current bounded maintenance chain and local absorption
python -m scripts.run_tests -q tests/test_maintenance_task_lease.py tests/test_maintenance_local_codex_foreman.py tests/test_maintenance_validation_execution.py tests/test_maintenance_corrective_continuation.py tests/test_maintenance_commit_execution.py tests/test_maintenance_commit_publication_recovery.py tests/test_maintenance_offline_absorption.py tests/test_maintenance_watchdog_closed_loop.py tests/test_maintenance_watchdog_publication.py tests/test_maintenance_activation_profiles.py

# Supplementary legacy chat/model loading safety
python -m scripts.run_tests -q tests/test_chat_service_lazy_loading.py tests/test_local_model.py tests/integration/test_chat_mistral_runtime.py

# Test-runner bootstrap and integration marker compatibility
python -m scripts.run_tests -q tests/test_integration_conftest_compat.py tests/test_run_tests_bootstrap_airlock.py

# Federation improvement custody runway
python -m scripts.run_tests -q tests/test_federated_improvement_candidate.py tests/test_federated_improvement_intake_receipt.py tests/test_federated_improvement_custody_runway.py tests/test_federated_improvement_local_variant_artifact.py tests/test_federated_improvement_lineage_comparison_receipt.py tests/test_federated_improvement_dissemination_receipt.py

# Prompt-boundary verifier
python scripts/verify_context_hygiene_prompt_boundaries.py

# Audit verifier
python scripts/verify_audits.py --strict

# Immutability verifier
python scripts/audit_immutability_verifier.py --manifest vow/immutable_manifest.json

# Docs dependency check and docs build
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
```

## Bounded diagnostic execution lifecycle

The [host-local diagnostic lifecycle reviewer guide](host_local_diagnostic_lifecycle_reviewer_guide.md)
maps the implemented admitted source evidence -> operator-confirmed diagnostic
write -> operator-confirmed exact rollback -> deletion-independent closure
path. Execution changes exactly the six runtime-owned diagnostic files and
preserves unrelated siblings; rollback deletes exactly
`sentientos_local_diagnostic_effect.json` and changes no sibling or other owned
file. Closure packages historical evidence below its external output root and
does not supply current runtime authority.

Focused proof is available without duplicating the complete guide:

```bash
python -m scripts.run_tests -q tests/test_host_local_diagnostic_execution_source_runtime.py tests/test_host_local_diagnostic_execution_runtime.py tests/test_host_local_diagnostic_rollback_runtime.py tests/test_host_local_diagnostic_lifecycle_closure.py
```

## Internal language / cultural layer

Internal and legacy cultural documentation remains available and is not removed by this overview. Reviewers who need term mapping should start with:
- `docs/PUBLIC_LANGUAGE_BRIDGE.md`
- `docs/enter_cathedral.md`
- `AGENTS.md` (repository governance ledger)

## Host embodiment substrate

See `docs/architecture/host_embodiment_substrate_phase1.md` and `docs/architecture/host_embodiment_substrate_phase2_read_only_discovery.md` and `docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md` and `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md` and `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md` for Host Embodiment Substrate phases 1 through 5.


### Host Embodiment Phase 4 Privilege Broker

See `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`. Phase 4 evaluates proposal receipts for future privileged-action eligibility only. Eligibility is not authorization, a broker receipt is not fulfillment, fan/PWM/thermal control remains blocked/deferred, and the future Actuation Fulfillment Layer is still required before any effect can occur.


### Host Embodiment Phase 5 Actuation Fulfillment Scaffold

See `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md`. Phase 5 creates fulfillment rehearsal plans and rehearsal receipts only. Fulfillment rehearsal is not real fulfillment, a rehearsal receipt is not an effect receipt, no host mutation occurs, and fan/PWM/thermal/power/service/cleanup actions remain blocked/deferred behind future control-plane admission, operator/policy approval, audit, rollback, effect receipt, and postcondition gates.


## Host Embodiment Execution Proof Wing

Next proof/readiness wing: `docs/architecture/host_embodiment_execution_proof_wing.md`. Execution readiness is not authorization; the future effect receipt schema is not proof of effect; the Runtime Supervisor does not restart/kill services; real actuation remains deferred.

## Host Embodiment Authorization Review Wing

Next review-only wing: `docs/architecture/host_embodiment_authorization_review_wing.md`. Authorization review is not authorization grant; the future authorization grant schema is not a real grant; real fulfillment remains deferred; real actuation remains deferred. Future cooling, power, service, and cleanup actions remain behind explicit future authorization, control-plane admission, audit, rollback, effect receipt, and postcondition checks.

### Controlled authorization + trace proof

The [Host Embodiment Controlled Authorization + Trace Wing](host_embodiment_controlled_authorization_and_trace_wing.md) adds a contract-only controlled authorization schema and a demo/proof-only host embodiment trace. The controlled authorization contract is not a live grant; the grant record is schema-only/future-use-only; the demo trace is reviewer proof only; real fulfillment and real actuation remain deferred.

Proof path: docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md

## Host Embodiment Reviewer Demo Trace

See `docs/architecture/host_embodiment_reviewer_demo_trace.md` for the one-command deterministic reviewer trace. Run `python scripts/build_host_embodiment_trace.py --format json`, `python scripts/build_host_embodiment_trace.py --format markdown`, or `python scripts/build_host_embodiment_trace.py --validate-only`. The demo trace is reviewer proof only, no host mutation occurs, PWM presence is not control authority, the controlled authorization contract is not a live grant, and grant/revocation records are schema-only/future-use-only.


Reviewer first-run proof bundle: `docs/architecture/reviewer_first_run_proof_bundle.md`.

Host live-grant readiness is documented in [Host Live-Grant Readiness Wing](host_live_grant_readiness_wing.md) (`docs/architecture/host_live_grant_readiness_wing.md`): live-grant readiness is not a live grant, the operator/policy approval packet is not approval, grant issue preflight does not issue a grant, and real actuation remains deferred.


Local authorization grant records are documented in [Host Local Authorization Grant Wing](host_local_authorization_grant_wing.md) (`docs/architecture/host_local_authorization_grant_wing.md`): a local authorization grant is authority metadata, not fulfillment; grant verification is not fulfillment authorization; real actuation remains deferred.

Reviewer proof link: [Host Fulfillment Authorization Consumption Wing](host_fulfillment_authorization_consumption_wing.md) documents the metadata-only authorization-consumption layer. Consuming authorization is not fulfillment; scope match is not execution; real actuation remains deferred.

Path: `docs/architecture/host_fulfillment_authorization_consumption_wing.md`.

Reviewer map: [Host Fulfillment Executor Contract Wing](host_fulfillment_executor_contract_wing.md) (`docs/architecture/host_fulfillment_executor_contract_wing.md`) follows fulfillment authorization consumption. Executor contract is not an executor; backend declaration does not load/invoke backend; dry-run plan is not dry-run execution; admission packet is not control-plane admission; real actuation remains deferred.


See also: [Host Dry-Run Execution Harness Wing](host_dry_run_execution_harness_wing.md) (`docs/architecture/host_dry_run_execution_harness_wing.md`), which is simulation-only; dry-run execution is not real fulfillment, dry-run result is not an effect receipt, dry-run receipt is not proof of host mutation, and real actuation remains deferred.

See also: [Host Dry-Run Effect Verification / Audit Closure Wing](host_dry_run_audit_closure_wing.md) (`docs/architecture/host_dry_run_audit_closure_wing.md`), which verifies dry-run evidence only; it is not a real effect receipt, not a real host postcondition check, not real rollback, not a production audit receipt, and real actuation remains deferred.


## Real effect capability admission link

See [Host Real Effect Capability Admission Wing](host_real_effect_capability_admission_wing.md) (`docs/architecture/host_real_effect_capability_admission_wing.md`): dry-run closure does not automatically permit real effects; real effect admission is not implementation, the admission decision does not authorize implementation or execution, the plan scaffold does not start implementation, cooling/hardware control remains blocked by default, and real actuation remains deferred.

For the first intentionally real but bounded effect, see the [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md), which only writes one explicit local diagnostic artifact and is not run by reviewer bundles by default.

Host embodiment proof now includes an explicit [local diagnostic effect pilot](host_local_diagnostic_effect_pilot_wing.md) and matching [exact artifact rollback pilot](host_local_diagnostic_exact_rollback_pilot_wing.md); reviewer bundles document but do not run either by default.

The [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md) (`docs/architecture/host_local_effect_transaction_ledger_wing.md`) adds metadata-only lifecycle integrity for the local diagnostic effect and exact rollback; it adds no new host effect and is not general cleanup or broader host control.

See also: [Host Steward / Delegated Runner Boundary Wing](host_steward_delegated_runner_boundary_wing.md) (`docs/architecture/host_steward_delegated_runner_boundary_wing.md`) for the next authority boundary after the local effect transaction ledger. It models broad top-level host-steward authority without granting delegated runners ambient authority.

- `docs/architecture/host_builtin_local_effect_runner_pilot_wing.md` — first actual delegated runner implementation; in-process only; supports only local diagnostic artifact write and exact-artifact rollback; not a general runner framework; no subprocess/shell/network/provider/prompt.

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.

## Workspace-scoped file update pilot

See [Host Workspace-Scoped File Effect Pilot Wing](host_workspace_file_effect_pilot_wing.md) (`docs/architecture/host_workspace_file_effect_pilot_wing.md`): the next bounded real-effect pilot after the runner transaction orchestrator creates or updates exactly one explicit file inside an explicit workspace root, captures preimage before replacement, verifies postcondition, supports exact-target rollback only, is not general filesystem access, is not cleanup, and does not use subprocess/shell/network/provider/prompt or hardware/service/power/fan/thermal authority.

See also: [Host Workspace File Runner / Transaction Integration Wing](host_workspace_file_runner_transaction_wing.md).

- Workspace file transaction orchestrator: see [Host Workspace File Transaction Orchestrator Wing](host_workspace_file_transaction_orchestrator_wing.md) for implemented single-target workspace update/rollback/ledger modes; the previous orchestration deferral is removed without adding general filesystem, cleanup, subprocess, shell, network, provider, prompt, or hardware/service/power/fan/thermal authority.

## Next workspace planning wing

Workspace change-set admission is documented in [Host Workspace Change Set Admission Controller](host_workspace_change_set_admission_wing.md) (`docs/architecture/host_workspace_change_set_admission_wing.md`): it is a bounded metadata-only eligibility gate before preflight, inspects supplied proposal metadata only, may write one caller-supplied admission artifact, and does not read workspace target files, check filesystem existence, compute filesystem digests, preflight, plan transactions, execute, rollback, verify replay, close lifecycle state, cleanup, schedule, or invoke subprocess/shell/network/provider/prompt/hardware/service/power/fan/thermal paths.

See [`Host Workspace Change Set Preflight / Planning Wing`](host_workspace_change_set_preflight_wing.md) (`docs/architecture/host_workspace_change_set_preflight_wing.md`) for the metadata-only layer that prepares bounded multi-target workspace changes but does not execute them, reads only explicitly declared target metadata/digests, performs no target writes, performs no rollback, invokes no runner/orchestrator, and is followed by bounded change-set transaction execution in the execution pilot wing.


Workspace change-set transaction execution is documented in [Host Workspace Change Set Transaction Execution Pilot Wing](host_workspace_change_set_execution_wing.md) (`docs/architecture/host_workspace_change_set_execution_wing.md`): it is the first bounded multi-target workspace execution layer, consumes passed preflight/transaction plans, uses existing single-target helpers, records partial state visibly, and does not grant general filesystem access or cleanup authority.


Workspace change-set execution verification is documented in [Host Workspace Change Set Execution Verification / Replay Audit Wing](host_workspace_change_set_execution_verification_wing.md) (`docs/architecture/host_workspace_change_set_execution_verification_wing.md`): it is a read-only replay-audit layer for completed change-set executions, reads only declared manifest targets, checks receipt/ledger/closure and optional rollback evidence, may write one caller-supplied verification artifact, and does not execute, rollback, cleanup, schedule, scan undeclared files, or invoke subprocess/shell/network/provider/prompt/hardware/service/power/fan/thermal paths.

Workspace change-set lifecycle closure is documented in [Host Workspace Change Set Lifecycle Closure Manifest Wing](host_workspace_change_set_lifecycle_closure_wing.md) (`docs/architecture/host_workspace_change_set_lifecycle_closure_wing.md`): it is a metadata-only sealing layer after verification that consumes supplied evidence JSON only, emits compact lifecycle closure statuses, may write one caller-supplied closure artifact, and does not read target files, recompute target filesystem digests, execute, rollback, verify replay, cleanup, schedule, recurse directories, expand wildcards, or invoke subprocess/shell/network/provider/prompt/hardware/service/power/fan/thermal paths.

The [Host Workspace Change Set Lifecycle Orchestration Wing](host_workspace_change_set_lifecycle_orchestration_wing.md) (`docs/architecture/host_workspace_change_set_lifecycle_orchestration_wing.md`) coordinates the existing admission, preflight/planning, optional execution, optional verification, and optional closure wings without adding target-file primitives, direct target reads, target digest recomputation, cleanup, scheduling, external tools, or provider/prompt authority.


## Repository mutation custody

The default `sentientosd` maintenance loop does not stage files, create commits, mutate branches, push, or create pull requests. It may emit deterministic metadata-only repository mutation handoffs for already-approved explicit-path proposals; those handoffs require external operator/Codex landing review and do not authorize mutation. `updater.py` / `sentientos-updater` is treated as an explicit operator-invoked legacy utility, not daemon default behavior.

### Repository mutation custody v2 sealing

Repository mutation handoffs now use `repository-mutation-handoff.v2`. A ready v2
handoff is metadata-only and requires an approved proposal, an approval/ledger
reference, exact `approved_paths` / `approved_path_digests` set equality, a
lowercase SHA-256 approval digest for every approved file, and an
`approved_source_revision` that exactly matches the read-only observed revision
from `git rev-parse HEAD`. Missing approval references, missing digest data, or
unknown source revisions are incomplete; digest mismatches, revision mismatches,
unsafe paths, outside-repository evidence, and approved-path/digest set
mismatches are contradicted. v1 artifacts remain historical review metadata and
are not sufficient for v2 readiness.

The daemon writes runtime handoff artifacts outside the repository worktree. The
resolved root precedence is: explicit injection,
`SENTIENTOS_REPOSITORY_MUTATION_HANDOFF_ROOT`,
`LOCALAPPDATA/SentientOS/repository_mutation_handoffs` on Windows,
`XDG_STATE_HOME/sentientos/repository_mutation_handoffs`, then
`~/.local/state/sentientos/repository_mutation_handoffs`. Roots equal to or
contained in the repository, including `.git`, are refused. Handoff emission uses
atomic JSON writes and must not create `integration/repository_mutation_handoffs`
or dirty the repository worktree.

No unused Git mutation convenience helper remains. The daemon-facing API is a
repository-mutation handoff reader, not a commit-state API: it does not stage
files, create commits, mutate branches, push, create pull requests, mark
proposals committed, adopt proposals, invoke providers, assemble prompts, or
expand runtime authority. External Codex/operator landing controls, including
finalizer, matrix, supervisor, and PR metadata guard, remain required.

## World-State Evidence Board

SentientOS includes a read-only World-State Evidence Board that normalizes bounded local evidence into deterministic snapshots and dashboard views. It separates observation, proposal, review, admission, execution, rollback, adoption, repository handoff, and repository landing, and it records contradiction/staleness posture without granting any runtime authority.

## Reviewed Genesis adoption custody

Genesis adoption is now documented as an explicit reviewed-candidate path: a
sealed packet, operator decision, separate control-plane admissions, exact
candidate execution, receipt/rollback evidence, and World-State projection. The
daemon remains proposal-only and does not approve or adopt candidates.

### Host privilege review and fulfillment rehearsal runtime

The host privilege review and fulfillment rehearsal runtime links the read-only host-resource observation runtime to the existing Privilege Broker and Actuation Fulfillment rehearsal builders during the same daemon tick. It consumes in-memory proposal-only receipts, obtains proposal-evaluation admission for metadata classification only, persists an external evidence bundle, projects read-only facts into World-State, and exposes `/api/world-state/host-privilege-review`. It does not grant privileged-effect admission, operator approval, real fulfillment, backend execution, host mutation, effect proof, or rollback execution. See `docs/architecture/host_privilege_review_rehearsal_runtime.md`.

Reviewer map: [Host Fulfillment Executor Contract Readiness Runtime](host_fulfillment_executor_contract_readiness_runtime.md) binds exact consumption custody to executor-contract review records. It is metadata-only: backend declarations are not loaded backends, dry-run plans are unexecuted, admission packets are not granted admission, and readiness receipts are not execution permission.

Reviewer map: [Host Dry-Run Execution Runtime](host_dry_run_execution_runtime.md) binds exact executor-readiness runtime custody to one deterministic in-process simulated backend run. It may report `dry_run_executed=true` for simulation only; real executor implementation, backend loading/invocation, future-execution admission, fulfillment, privileged-effect admission, host mutation, and effect proof remain false or absent.

Canonical navigation: `docs/architecture/sentientos_trajectory_and_missing_organs.md`, `docs/architecture/reviewer_release_readiness_index.md`, `docs/architecture/host_actuation_safety_gate_wing.md`, and `docs/architecture/host_steward_delegated_runner_boundary_wing.md`.
