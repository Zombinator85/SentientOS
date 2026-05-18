# SentientOS Trajectory and Missing Organs

The [Host Actuation Safety Gate Wing](host_actuation_safety_gate_wing.md) (`docs/architecture/host_actuation_safety_gate_wing.md`) is now the metadata-only organ that declares hardware allowlist, backend, bounds, cooldown, panic, scope, assessment, and satisfaction gates before any future live authorization review. Real actuation remains deferred.
## Reviewer first-run proof bundle

Reviewers can generate the local non-mutating host-embodiment proof archive with `python scripts/build_reviewer_proof_bundle.py --output-dir /tmp/sentientos-reviewer-proof`; see [Reviewer First-Run Proof Bundle](reviewer_first_run_proof_bundle.md) (`docs/architecture/reviewer_first_run_proof_bundle.md`). It uses fake/sample telemetry by default, performs no live host collection by default, and performs no host mutation.

## What SentientOS is becoming

SentientOS is becoming a user-space operating substrate for governed AI
autonomy. It does not replace Windows, macOS, Linux, or any host kernel. It runs
above the host OS and organizes installer/bootstrap flow, first boot,
shell/dashboard affordances, local model runtime, memory/context/reflection,
perception and embodiment telemetry, bounded GUI/browser interaction,
hardware/driver awareness, audit/immutability checks, control-plane authority,
governed self-amendment, and federation evidence custody.

The practical trajectory is an AI operating layer with explicit admission and
receipts. It should make local capabilities visible, propose bounded work from
observations, gate sensitive action through governance, execute only admitted
host effects, and leave enough audit evidence for an operator or reviewer to
reconstruct what happened. Capabilities that are only implied by this trajectory
are listed below as missing or deferred rather than claimed as implemented.

Host Embodiment Substrate Phase 1 is the first observe/model substrate for this
path; see `docs/architecture/host_embodiment_substrate_phase1.md` and `docs/architecture/host_embodiment_substrate_phase2_read_only_discovery.md` and `docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md` and `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`. It adds a
Capability Registry, Hardware/Sensor Inventory Manifest, and read-only Host
Resource Governor scaffold while keeping Privilege Broker and Actuation
Fulfillment Layer requirements ahead of any future host actuation. Direct
fan/PWM control remains deferred.

## What already exists

The repository already contains these major subsystem surfaces:

| Area | Existing paths | Current status |
| --- | --- | --- |
| Installer/setup/bootstrap | `installer/setup_installer.py`, `setup_env.sh`, `scripts/install_locked.py`, `scripts/bootstrap_node.py`, `scripts/bootstrap_cathedral.py`, `sentientos/runtime/bootstrap.py`, `sentientos/node/__main__.py` | Offline/deterministic setup helpers, dependency/bootstrap paths, node bootstrap helpers, log creation, manifest artifact verification, and smoke-test hooks. |
| Windows install path | `README.md`, `docs/WINDOWS_LOCAL_MODEL_SETUP.md`, `run_cathedral.bat`, `launch_sentientos.bat`, `Start-All.ps1`, `Stop-All.ps1`, `scripts/package_launcher.py` | Windows-oriented run and packaging documentation/scripts exist. This is a user-space Windows path, not a kernel or driver replacement. |
| First boot wizard | `sentientos/first_boot.py`, `tests/test_first_boot.py` | First boot records approval, driver review, Codex mode/cadence, architect autonomy flag, federation peer settings, completion flag, ledger rows, and pulse events. |
| Shell/dashboard/start menu/file explorer/Codex console | `sentientos/shell/__init__.py`, `sentientos/shell/cli.py`, `apps/dashboard/main.py`, `dashboard_ui/`, `scripts/streamlit_dashboard.py`, `scripts/launcher_gui.py` | Shell abstractions cover start menu, taskbar, sandboxed file explorer, install simulation, Codex expansion request files, event logging, and dashboard surfaces. |
| Local model/chat runtime | `sentientos/local_model.py`, `sentientos/chat_service.py`, `model_bridge.py`, `tests/test_local_model.py`, `tests/test_chat_service_lazy_loading.py`, `tests/integration/test_chat_mistral_runtime.py` | Local model loading supports placeholder/null, echo, GGUF/llama.cpp, and local transformers backends with local-file defaults and safe fallback behavior. Chat service lazy loading is tested. |
| Memory/context/reflection storage | `memory_manager.py`, `memory_governor.py`, `sentientos/memory/`, `sentientos/meta/reflection_loop.py`, `reflection_log_cli.py`, `api/actuator.py` | Memory append/read, reflection storage, memory pressure/governor, pulse views, and action-result reflection surfaces exist. Context hygiene lives under `sentientos/context_hygiene/`. |
| Autonomy runtime composition | `sentientos/autonomy/runtime.py`, `sentientos/autonomy/state.py`, `sentientos/autonomy/rehearsal.py`, `sentientos/autonomy/curiosity_loop.py`, `sentientos/orchestrator.py`, `scripts/orchestrator_daemon.py` | Runtime/state/rehearsal and orchestrator pieces exist. They should be treated as governed composition surfaces, not blanket authority. |
| ASR/TTS/screen OCR/perception | `mic_bridge.py`, `tts_bridge.py`, `tts_service.py`, `ocr_pipeline.py`, `ocr_utils.py`, `scripts/perception/screen_adapter.py`, `sentientos/perception_api.py` | Speech recognition, text-to-speech, OCR, screen observation normalization, and perception telemetry surfaces exist. Legacy perception paths are explicitly marked non-authoritative/proposal-oriented in several modules. |
| GUI control shim | `ui_controller.py`, `input_controller.py`, `sentientos/innervation.py` | UI/key/mouse abstractions and panic/permission/policy checks exist. These are shims and should not be read as blanket host control. |
| Browser automation | `sentientos/agents/browser_automator.py`, `sentientos/oracle_relay.py`, `browser_voice.py` | Browser automation can be configured with enable flags, domain allowlists, daily budgets, panic checks, audit logging, and council checks for posting. Oracle relay contains Playwright session machinery. |
| Driver manager and hardware/device awareness | `sentientos/daemons/driver_manager.py`, `config/hardware_profile.json`, `gpu_autosetup.py`, `tests/test_first_boot.py` | Device probing/recommendation, candidate driver catalog, suggestions, whitelisted vendors, and veil-pending install requests exist. This is not blanket hardware control. |
| Embodiment fusion/ingress/proposal/governance/fulfillment/avatar state | `sentientos/embodiment_fusion.py`, `sentientos/embodiment_ingress.py`, `sentientos/embodiment_proposals.py`, `sentientos/embodiment_proposal_review.py`, `sentientos/embodiment_governance_bridge.py`, `sentientos/embodiment_fulfillment.py`, `sentientos/embodiment/avatar_state.py`, `godot_avatar_demo/` | Embodiment snapshots, ingress gates, proposal records, review receipts, governance bridge candidates, fulfillment candidates/receipts, and avatar state/demo surfaces exist. Fulfillment receipts are currently non-authoritative evidence, not proof of side effects. |
| Control-plane kernel and admission authority | `sentientos/control_plane_kernel.py`, `control_plane/`, `sentientos/runtime_governor.py`, `docs/control_plane_authority_map.md`, `tests/test_control_plane_kernel.py` | Phase-aware admission, authority classes, decisions, process-local dedupe, runtime governor delegation, and machine-readable decision rows exist. |
| ArchitectDaemon / GenesisForge / Codex self-amendment arc | `architect_daemon.py`, `codex/autogenesis.py`, `sentientos/forge.py`, `sentientos/forge_cli/`, `sentientos/forge_queue.py`, `sentientos/protected_mutation_intent.py`, `tests/test_architect_daemon.py`, `tests/test_genesis_forge.py`, `tests/test_autogenesis_loop.py` | Gap scanning, lineage annotation, review symmetry, forge CLI/status/queue, and protected mutation intent surfaces exist. These are governed proposal/review paths, not unapproved self-modification. |
| Audit/immutability/context-boundary verification | `scripts/verify_audits.py`, `verify_audits.py`, `audit_immutability.py`, `scripts/audit_immutability_verifier.py`, `scripts/verify_context_hygiene_prompt_boundaries.py`, `sentientos/context_hygiene/`, `docs/architecture/context_hygiene_spine.md` | Audit verification, immutability checks, prompt/context boundary scans, provider denial custody, and source-kind safety contracts exist. |
| Federation improvement custody runway | `sentientos/federation/improvement_candidate.py`, `sentientos/federation/improvement_intake_receipt.py`, `sentientos/federation/improvement_custody_runway.py`, `sentientos/federation/improvement_local_variant_artifact.py`, `sentientos/federation/improvement_lineage_comparison_receipt.py`, `sentientos/federation/improvement_dissemination_receipt.py`, `docs/architecture/federated_improvement_custody_runway.md` | Federation improvement artifacts and receipts exist as evidence/readiness/custody surfaces only. They do not transport, adopt, apply, merge, install, or execute by themselves. |

## What works in concert

The intended whole-system loop is:

1. Install or bootstrap the node and verify pinned/local artifacts.
2. Run first boot, obtain required local approval, detect hardware, and configure
   driver review, Codex/autonomy posture, and federation peer metadata.
3. Run the local model/chat runtime or placeholder backend under local-file and
   fallback rules.
4. Observe local screen/audio/vision/feedback/browser context through perception
   adapters and legacy shims.
5. Store eligible memory, context, and reflection records only through the
   applicable memory/context paths and gates.
6. Fuse observations into embodiment snapshots and classify embodied pressure,
   privacy posture, retention posture, and risk flags.
7. Convert eligible pressure into proposal, governance bridge, and fulfillment
   candidates.
8. Gate sensitive candidates through the control plane, runtime governor,
   council/review surfaces, and policy checks.
9. Execute only host actions that have an admitted, explicit, local authority
   path; where fulfillment is only a receipt artifact, do not treat it as a real
   effect.
10. Write audit, immutability, decision, and receipt evidence.
11. Detect capability gaps from logs/tests/probes and draft governed amendments
    through ArchitectDaemon, GenesisForge/autogenesis, or forge/Codex review
    flows.
12. Optionally share metadata/evidence through federation custody artifacts, with
    local adoption remaining separate and non-automatic.

## Capabilities the repo supports today

Supported facts in the current repository state:

- Install/bootstrap helpers exist for deterministic/offline setup, dependency
  handling, node/bootstrap scripts, log creation, manifest artifact verification,
  and smoke-test hooks.
- A local model/chat path exists, including placeholder/null, echo, GGUF/llama.cpp,
  and local transformers loading. Local transformers loading uses local files and
  defaults custom model code execution off unless explicitly opted in.
- Memory, context, and reflection storage surfaces exist through `memory_manager.py`,
  `memory_governor.py`, `sentientos/memory/`, `sentientos/meta/reflection_loop.py`,
  and action/reflection logging paths.
- Perception and embodiment telemetry surfaces exist for audio, screen/OCR,
  vision/multimodal/feedback/gaze-shaped observations, normalized perception
  events, and embodiment snapshots.
- A GUI control shim exists through `ui_controller.py` and `input_controller.py`,
  including dummy and optional platform backends, logging, panic handling, and
  permission/policy hooks.
- Browser automation exists through `sentientos/agents/browser_automator.py` and
  related relay/demo surfaces, with enable flags, allowlists, budgets, panic
  checks, and audit hooks.
- TTS, ASR, and screen OCR surfaces exist through `tts_bridge.py`, `tts_service.py`,
  `mic_bridge.py`, `ocr_pipeline.py`, `ocr_utils.py`, and
  `scripts/perception/screen_adapter.py`.
- Hardware driver awareness exists through `sentientos/daemons/driver_manager.py`,
  with device reports, recommendations, package lists, whitelisted vendors,
  suggestions, and veil-protected install requests.
- First-boot Codex/federation configuration exists through `sentientos/first_boot.py`.
- Governed self-amendment exists as gap scanning, lineage, review, protected
  mutation intent, forge queue/status/CLI, and tests. It is not automatic
  unapproved self-modification.
- Federation evidence custody exists for improvement candidate, intake, custody
  runway, local variant, lineage comparison, and dissemination receipts.

## Claims not yet supported

The following claims are not supported by the current repository state and should
not be made as implemented capabilities:

- Direct fan/PWM control is deferred unless and until a concrete, tested module is
  added. No direct fan/PWM controller is claimed here.
- Blanket hardware control is not implemented. The driver manager recommends and
  queues/records driver actions; it is not general host-device authority.
- Host kernel replacement is not implemented and is outside the stated model.
  SentientOS is a user-space layer above Windows/macOS/Linux.
- Automatic remote execution is not implemented.
- Forced federation adoption is not implemented.
- Provider invocation is not implemented as an approved runtime capability.
  Existing provider-denial and provider-readiness artifacts are custody/metadata
  surfaces; legacy relay/demo code must not be interpreted as approved provider
  transport authority.
- Prompt assembly/export for provider invocation is not implemented as an
  approved runtime capability. Prompt-related phase artifacts are dry-run,
  boundary, denial, or metadata surfaces unless a future admitted implementation
  says otherwise.
- Autonomous unapproved self-modification is not implemented. The self-amendment
  arc is proposal/review/governance oriented.
- Production execution from readiness, rehearsal, receipt, or custody artifacts is
  not implemented. Receipts can support review; they do not execute themselves.

## Missing organs

These are concrete subsystems required by the implied trajectory but not yet
complete as canonical, production-ready organs:

### 1. Host Resource Governor

A canonical resource governor should collect CPU, RAM, GPU, disk, network,
thermal, and fan telemetry first. Any future actions, including fan/PWM, CPU/GPU
limits, network throttles, or process controls, must come later behind policy,
hardware allowlists, receipts, and rollback behavior.

Proof required:

- Tests for telemetry parsing, missing-sensor handling, policy denial, and no-op
  behavior when actions are disabled.
- Audit receipt for every telemetry snapshot and every denied/deferred action.
- Fail-closed behavior when sensor data is stale, contradictory, privileged, or
  unavailable.
- No implicit authority to change host resources.
- Operator override and panic handling that stops future actions and marks state
  degraded.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_host_resource_governor.py`.

### 2. Privilege Broker

A single canonical broker should mediate privileged host actions instead of each
subsystem inventing its own escalation path. The broker should identify actor,
authority class, requested effect, target, proof requirements, admission decision,
and operator override state.

Proof required:

- Tests for allow/deny/defer/quarantine outcomes, unknown action denial, and
  duplicate request handling.
- Audit receipt for every request and decision.
- Fail-closed behavior when policy, operator approval, or proof is missing.
- No implicit authority from subsystem-local helper calls.
- Operator override and panic handling with visible blocked/degraded state.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_privilege_broker.py`.

### 3. Actuation Fulfillment Layer

Approved candidates need a canonical layer that turns admitted proposals into
real effects with receipts. This layer should distinguish candidate, admission,
execution attempt, result, rollback, and audit receipt. It must not confuse a
fulfillment candidate or receipt with proof that a side effect occurred.

Proof required:

- Tests for candidate-to-admission-to-effect lifecycle, denied candidates, dry-run
  candidates, rollback paths, and idempotency.
- Audit receipt for each attempted, skipped, denied, completed, and rolled-back
  effect.
- Fail-closed behavior when admission is missing or stale.
- No implicit authority from proposal existence.
- Operator override and panic handling before and during fulfillment.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_actuation_fulfillment_layer.py`.

### 4. Hardware/Sensor Inventory Manifest

A durable local manifest should inventory sensors, devices, power/thermal
capabilities, available resource telemetry, driver posture, privacy class, and
operator consent posture. It should be local-first and should not grant authority
by itself.

Proof required:

- Tests for inventory creation, update, redaction, schema migration, and missing
  hardware.
- Audit receipt for inventory snapshots and schema changes.
- Fail-closed behavior when a device capability is unknown or unverified.
- No implicit authority to actuate hardware from inventory entries.
- Operator override and panic handling that can mark devices disabled/degraded.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_hardware_sensor_inventory_manifest.py`.

### 5. Runtime Supervisor

A runtime supervisor should maintain a service registry, health status, restart
policy, safe shutdown, panic shutdown, dependency order, and degraded state for
SentientOS services. It should coordinate daemons without granting them new
host authority.

Proof required:

- Tests for service registration, health transitions, bounded restarts, safe
  shutdown, panic shutdown, and degraded dependencies.
- Audit receipt for service lifecycle events and restart decisions.
- Fail-closed behavior when restart budgets or health proofs fail.
- No implicit authority for services to self-escalate.
- Operator override and panic handling that stops or disables services.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_runtime_supervisor.py`.

### 6. Capability Registry

A machine-readable registry should state what the node can sense, remember,
decide, act on, and federate. It should include capability provenance, status,
policy owner, proof command, and whether the capability is read-only,
proposal-only, dry-run, or effect-capable.

Proof required:

- Tests for registry schema, capability lookup, unsupported capability denial,
  and drift detection against docs/tests.
- Audit receipt for registry changes and capability posture changes.
- Fail-closed behavior when a capability is absent or contradictory.
- No implicit authority from capability names alone.
- Operator override and panic handling that can mark capabilities blocked.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_capability_registry.py`.

### 7. Local Model Authority Map

A local model authority map should record each model's posture: escrowed local
artifact, local custom-code setting, remote/provider posture, allowed tools,
context access posture, and proof commands. It should make provider invocation
and custom code posture explicit per model.

Proof required:

- Tests for model inventory, local-only defaults, custom-code opt-in, provider
  denial, and missing artifact handling.
- Audit receipt for model posture changes and load decisions.
- Fail-closed behavior when artifact, checksum, or authority posture is unknown.
- No implicit provider authority from model configuration.
- Operator override and panic handling that disables model loads or tool access.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_local_model_authority_map.py`.

### 8. World-State Board

A live board should derive pending, degraded, approved, blocked, and fulfilled
state from logs, decisions, receipts, and supervisor health. It should be a view
of evidence, not a decision engine.

Proof required:

- Tests for state derivation from representative logs, contradiction handling,
  stale data, and degraded views.
- Audit receipt for board snapshots or exports.
- Fail-closed behavior when source logs are missing or inconsistent.
- No implicit authority to execute from board display state.
- Operator override and panic handling shown clearly in the board.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_world_state_board.py`.

### 9. Federation Transport Envelope

A federation transport envelope should exchange metadata-only receipts and
lineage evidence without adoption, execution, merge, apply, install, or remote
control. It should preserve local review boundaries and make remote origin and
trust posture explicit.

Proof required:

- Tests for envelope schema, signature/identity metadata, local rejection,
  replay protection, and non-adoption.
- Audit receipt for inbound/outbound metadata envelopes.
- Fail-closed behavior when origin, schema, signature, or policy is invalid.
- No implicit authority from receipt delivery.
- Operator override and panic handling that disables transport.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_federation_transport_envelope.py`.

### 10. External Reviewer Demo Script

A safe reviewer demo should show one end-to-end path: install or bootstrap,
observe, write memory/context, produce a proposal, gate it, audit it, and export
proof. It should be deterministic, local, non-destructive, and explicit about
which steps are simulated.

Proof required:

- Tests for the demo script in a temporary workspace with no real host side
  effects.
- Audit receipt for every demo step.
- Fail-closed behavior on missing dependencies or unexpected host access.
- No implicit authority outside the demo workspace.
- Operator override and panic handling that aborts the demo safely.
- Docs proof command, for example `python -m scripts.run_tests -q tests/test_external_reviewer_demo_script.py`.

## Build order

Recommended phased order:

- **Phase A: Capability registry + whole-system map.** Establish one
  machine-readable source for supported, proposal-only, dry-run, blocked, and
  missing capabilities, and keep this document aligned with it.
- **Phase B: Hardware/sensor inventory manifest.** Record durable local inventory
  of devices, sensors, drivers, privacy posture, and resource telemetry
  availability without granting control.
- **Phase C: Host resource governor read-only telemetry.** Add read-only CPU,
  RAM, GPU, disk, network, thermal, and fan telemetry. Fan/PWM remains deferred.
- **Phase D: Privilege broker.** Route privileged host actions through one
  auditable broker and deny unknown paths by default.
- **Phase E: Actuation fulfillment layer.** Convert approved candidates into
  real effects only through admitted, receipt-producing fulfillment.
- **Phase F: Runtime supervisor.** Add registry, health, restart policy, safe
  shutdown, panic shutdown, and degraded service state.
- **Phase G: Federation transport envelope.** Exchange metadata-only custody
  receipts with no adoption or execution.
- **Phase H: Optional bounded host resource actions.** Consider fan/PWM or other
  resource actions only after telemetry, policy, hardware allowlists, privilege
  brokering, operator override, and rollback receipts exist.

## Safety/proof requirements summary

Every missing organ should satisfy the same baseline before being described as
implemented:

- Focused tests cover normal, denied, degraded, missing-dependency, and panic
  paths.
- Audit receipts exist for inputs, decisions, outputs, denials, and errors.
- Fail-closed behavior is the default for missing policy, missing proof,
  unavailable sensors, stale data, unknown capabilities, or invalid federation
  metadata.
- No implicit authority is inferred from observation, memory, proposal,
  readiness, receipt, dashboard state, or federation delivery.
- Operator override and panic handling are explicit, tested, logged, and visible
  in state surfaces.
- A docs proof command is listed for reviewers and can be run from the repository
  root.


### Host Embodiment Phase 3 policy receipts

Phase 3 is documented in `docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md`. It converts pressure reports into proposal receipts only: proposal receipts are not effects, policy decisions are not authorization, PWM presence is not control authority, and future cooling/power/service/cleanup candidates require the future Privilege Broker and Actuation Fulfillment Layer.


### Host Embodiment Phase 4 privilege broker eligibility

Phase 4 is documented in `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`. It classifies proposal receipts for future privileged-action eligibility only. Eligibility is not authorization, a broker receipt is not fulfillment, and direct fan/PWM/thermal control, service restart, power mutation, cleanup mutation, package/driver install, provider invocation, network egress, prompt assembly, federation transport/sync/adoption, and remote execution remain blocked behind future gates and the future Actuation Fulfillment Layer.


### Host Embodiment Phase 5 actuation fulfillment scaffold

Phase 5 is documented in `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md`. It adds the Actuation Fulfillment Layer scaffold as rehearsal-only metadata: fulfillment rehearsal is not real fulfillment, a rehearsal receipt is not an effect receipt, and no host mutation occurs. Direct fan/PWM/thermal control, service restart, power profile mutation, cleanup/deletion, process killing, package/driver installation, provider invocation, network egress, prompt assembly, federation transport/sync/adoption, and remote execution remain blocked/deferred behind future control-plane admission, operator/policy approval, audit, rollback, effect receipt, and postcondition gates.


## Host Embodiment Execution Proof Wing

Next proof/readiness wing: `docs/architecture/host_embodiment_execution_proof_wing.md`. Execution readiness is not authorization; the future effect receipt schema is not proof of effect; the Runtime Supervisor does not restart/kill services; real actuation remains deferred.

## Host Embodiment Authorization Review Wing

See `docs/architecture/host_embodiment_authorization_review_wing.md`. This next organ after the Execution Proof Wing records metadata-only authorization review packets, decisions, receipts, and a future grant schema placeholder. Authorization review is not authorization, the future authorization grant schema is not a real grant, real fulfillment remains deferred, and real actuation remains deferred.

## Controlled Authorization + Trace Wing

The [Host Embodiment Controlled Authorization + Trace Wing](host_embodiment_controlled_authorization_and_trace_wing.md) is now represented as the next non-mutating organ after Authorization Review: contract-only controlled authorization, schema-only/future-use-only grant and revocation records, metadata-only ledger, and a reviewer demo trace. Live authorization, real fulfillment, real actuation, rollback execution, fan/PWM control, thermal actuation, power mutation, service restart, and cleanup/delete remain missing/deferred organs.

Proof path: docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md

## Host Embodiment Reviewer Demo Trace

See `docs/architecture/host_embodiment_reviewer_demo_trace.md`. The external reviewer demo script now has a deterministic metadata-only thermal+PWM trace export. It is reviewer proof only: no live host collection by default, no live authorization, no effect, no host mutation, and PWM presence is not control authority.

### Host Live-Grant Readiness Wing

See [Host Live-Grant Readiness Wing](host_live_grant_readiness_wing.md) (`docs/architecture/host_live_grant_readiness_wing.md`). It sits after Host Actuation Safety Gates and before any future authorize/fulfill/effect path. It is readiness/preflight only; real actuation remains deferred.

- [Host Local Authorization Grant Wing](host_local_authorization_grant_wing.md): implemented bounded authorization-record lifecycle; fulfillment and actuation remain deferred.

Path link: `docs/architecture/host_local_authorization_grant_wing.md`.

Implemented organ link: [Host Fulfillment Authorization Consumption Wing](host_fulfillment_authorization_consumption_wing.md) adds metadata-only pre-fulfillment grant consumption checks while real fulfillment and real actuation remain deferred.

Path: `docs/architecture/host_fulfillment_authorization_consumption_wing.md`.

- [Host Fulfillment Executor Contract Wing](host_fulfillment_executor_contract_wing.md) records metadata-only executor prerequisites after fulfillment authorization consumption; it is not an executor and real actuation remains deferred.

Proof path: `docs/architecture/host_fulfillment_executor_contract_wing.md`.


See also: [Host Dry-Run Execution Harness Wing](host_dry_run_execution_harness_wing.md) (`docs/architecture/host_dry_run_execution_harness_wing.md`), which is simulation-only; dry-run execution is not real fulfillment, dry-run result is not an effect receipt, dry-run receipt is not proof of host mutation, and real actuation remains deferred.

- Host Dry-Run Effect Verification / Audit Closure Wing: `docs/architecture/host_dry_run_audit_closure_wing.md`. Dry-run effect verification is not a real effect receipt; dry-run postcondition verification is not a real host postcondition check; dry-run rollback rehearsal is not real rollback; dry-run audit closure is not a production audit receipt; real actuation remains deferred.


## Real effect capability admission link

See [Host Real Effect Capability Admission Wing](host_real_effect_capability_admission_wing.md) (`docs/architecture/host_real_effect_capability_admission_wing.md`): dry-run closure does not automatically permit real effects; real effect admission is not implementation, the admission decision does not authorize implementation or execution, the plan scaffold does not start implementation, cooling/hardware control remains blocked by default, and real actuation remains deferred.

The first bounded real-effect pilot is the [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md): one explicit local diagnostic artifact write, not hardware/service/power/cleanup control.

The trajectory now includes a bounded [Host Local Diagnostic Exact Artifact Rollback Pilot Wing](host_local_diagnostic_exact_rollback_pilot_wing.md): the first real rollback, limited to the exact diagnostic artifact and not general cleanup.

- [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md): metadata-only integrity ledger for the Tier-1 local diagnostic effect and exact rollback lifecycle before broader effect implementation.

See also: [Host Steward / Delegated Runner Boundary Wing](host_steward_delegated_runner_boundary_wing.md) (`docs/architecture/host_steward_delegated_runner_boundary_wing.md`) for the next authority boundary after the local effect transaction ledger. It models broad top-level host-steward authority without granting delegated runners ambient authority.

## Bounded Built-In Runner Pilot

`docs/architecture/host_builtin_local_effect_runner_pilot_wing.md` closes the first delegated-runner organ only for bounded in-process local diagnostic artifact write and exact-artifact rollback. General runners and hardware/service/power/fan/thermal/cleanup authority remain missing or blocked/deferred.

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.

## Workspace-scoped file update pilot

The trajectory now includes [Host Workspace-Scoped File Effect Pilot Wing](host_workspace_file_effect_pilot_wing.md): one explicit workspace-scoped file target, preimage capture, postcondition verification, production audit, and exact-target rollback. General filesystem access, cleanup, recursive/wildcard/unrelated deletion, subprocess/shell/network/provider/prompt, and hardware/service/power/fan/thermal authority remain missing or blocked/deferred organs.

See also: [Host Workspace File Runner / Transaction Integration Wing](host_workspace_file_runner_transaction_wing.md).

- Workspace file transaction orchestrator: see [Host Workspace File Transaction Orchestrator Wing](host_workspace_file_transaction_orchestrator_wing.md) for implemented single-target workspace update/rollback/ledger modes; the previous orchestration deferral is removed without adding general filesystem, cleanup, subprocess, shell, network, provider, prompt, or hardware/service/power/fan/thermal authority.

## Next workspace planning wing

See [`Host Workspace Change Set Preflight / Planning Wing`](host_workspace_change_set_preflight_wing.md) (`docs/architecture/host_workspace_change_set_preflight_wing.md`) for the metadata-only layer that prepares bounded multi-target workspace changes but does not execute them, reads only explicitly declared target metadata/digests, performs no target writes, performs no rollback, invokes no runner/orchestrator, and leaves future change-set execution deferred.


Workspace change-set transaction execution now exists as a bounded pilot in [Host Workspace Change Set Transaction Execution Pilot Wing](host_workspace_change_set_execution_wing.md). It narrows multi-target workspace execution to explicit manifest targets and leaves general filesystem access, cleanup, services, power, hardware, fan/PWM, thermal, network, provider, prompt, subprocess, and shell authority blocked or deferred.


The [Host Workspace Change Set Lifecycle Orchestration Wing](host_workspace_change_set_lifecycle_orchestration_wing.md) (`docs/architecture/host_workspace_change_set_lifecycle_orchestration_wing.md`) coordinates the existing admission, preflight/planning, optional execution, optional verification, and optional closure wings without adding target-file primitives, direct target reads, target digest recomputation, cleanup, scheduling, external tools, or provider/prompt authority.
