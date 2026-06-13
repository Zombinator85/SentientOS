# Reviewer Release-Readiness Proof Index

The [Host Actuation Safety Gate Wing](host_actuation_safety_gate_wing.md) (`docs/architecture/host_actuation_safety_gate_wing.md`) adds metadata-only safety gate proof records to the reviewer bundle. Safety gates are not authorization; hardware allowlists do not grant control; OS backend declarations do not load/invoke backends; panic stop contracts do not execute panic stop; real actuation remains deferred.
## Reviewer first-run proof bundle

Reviewers can generate the local non-mutating host-embodiment proof archive with `python scripts/build_reviewer_proof_bundle.py --output-dir /tmp/sentientos-reviewer-proof`; see [Reviewer First-Run Proof Bundle](reviewer_first_run_proof_bundle.md) (`docs/architecture/reviewer_first_run_proof_bundle.md`). It uses fake/sample telemetry by default, performs no live host collection by default, and performs no host mutation.


## Codex whole-system landing doctrine
For Codex workflow/governance tasks, review the root doctrine and linked templates:

- `AGENTS.md` (Codex Agent Operating Instructions + Whole-System Codex Operating Doctrine)
- `docs/development/codex_whole_system_task_template.md`
- `docs/development/codex_narrow_repair_task_template.md`
- `docs/development/codex_validation_and_landing_contract.md`
- `docs/development/codex_pr_metadata_guard.md`
- `scripts/run_work_item_review_packet_matrix.py`

These define whole-system default landing posture, narrow-repair exception posture, and validation/failure-classification reporting contract.

## What this index is

This is a reviewer-facing map of the currently implemented proof surfaces for the
recent SentientOS hardening and federation-improvement work. It is meant to help
a technical reviewer move from the public overview to concrete tests, scripts,
and custody artifacts without reconstructing context from scattered PRs.

This index is not a release announcement, not a production-readiness claim, and
not a promise of provider invocation, federation transport, automatic adoption,
remote execution, or merge/apply/install behavior.

For the broader user-space operating-substrate trajectory and the concrete
missing subsystems still required, see
`docs/architecture/sentientos_trajectory_and_missing_organs.md`.

Host Embodiment Substrate Phase 1 is covered by
`docs/architecture/host_embodiment_substrate_phase1.md` and `docs/architecture/host_embodiment_substrate_phase2_read_only_discovery.md`. It adds the
Capability Registry, Hardware/Sensor Inventory Manifest, and read-only Host
Resource Governor scaffold. Privilege Broker and Actuation Fulfillment Layer
remain future gates for any host action; direct fan/PWM control remains deferred. Phase 4 broker eligibility is documented in `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md` and still does not authorize or fulfill host action.


The [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md) (`docs/architecture/host_local_effect_transaction_ledger_wing.md`) records the local diagnostic effect plus exact rollback lifecycle, detects open/orphaned/incomplete/contradicted/closed transactions, and adds no new host effect.

## Current implemented proof surfaces

### Control plane / authority admission

`tests/test_control_plane_kernel.py` covers explicit authority admission,
admission status visibility, and bounded process-local TTL idempotency. The
current posture is explicit admission, not implicit runtime authority.

### Maintenance degradation / fail-stop behavior

`tests/test_sentientosd_runtime_closure.py` covers runtime closure behavior,
maintenance forge/merge admission gating, and structured degradation when a
maintenance tick fails. Denied maintenance admission does not run forge or merge
ticks.

### Federation trust ledger recovery

`tests/test_trust_ledger.py` and `sentientos/tests/test_trust_ledger_recovery.py`
cover trust ledger state loading, event replay fallback, and degraded handling
for malformed state/events. Current recovery is startup recovery from local state
or local events, not a cross-process mutation-locking guarantee.

### Federation probe prioritization

`tests/test_trust_ledger.py` covers deterministic prioritization of suspicious
federation peers for probing. This is prioritization evidence only; it does not
create transport, sync, or enforcement authority by itself.

### Chat/model loading safety

`tests/test_chat_service_lazy_loading.py`, `tests/test_local_model.py`, and
`tests/integration/test_chat_mistral_runtime.py` cover lazy chat model loading and
local transformer loading defaults. Importing chat service code does not load the
model, and local custom model code execution defaults to `trust_remote_code=False`
unless explicitly opted in.

### Test runner bootstrap reliability

`tests/test_run_tests_bootstrap_airlock.py` and
`tests/test_integration_conftest_compat.py` cover the focused test-airlock path
and integration marker compatibility. The focused proof suites should not require
a broad runtime dependency install before collection.

### Work item lifecycle handoff planning

`sentientos/work_item_lifecycle_handoff.py`, `scripts/plan_work_item_handoff.py`, `tests/test_work_item_lifecycle_handoff.py`, and `tests/test_plan_work_item_handoff_script.py` cover deterministic metadata-only next-surface planning from normalized intake packets. This surface does not invoke lifecycle orchestration and does not perform workspace execution.

See `docs/architecture/task_work_item_lifecycle_handoff_planner_wing.md`.

`sentientos/work_item_lifecycle_dry_run_adapter.py`, `scripts/run_work_item_dry_run.py`, `tests/test_work_item_dry_run_adapter.py`, and `tests/test_run_work_item_dry_run_script.py` provide a bounded metadata-only adapter that consumes normalized intake + handoff artifacts and invokes workspace lifecycle orchestration in `dry_run_full_lifecycle` mode only when explicit eligibility checks pass.

See `docs/architecture/task_work_item_lifecycle_dry_run_adapter_wing.md`.

Work item lifecycle attestation index verification is documented in `docs/architecture/task_work_item_lifecycle_attestation_index_verifier_wing.md` with metadata-only authority boundaries.

Work item lifecycle attestation review digest generation is documented in `docs/architecture/task_work_item_lifecycle_attestation_review_digest_wing.md` with metadata-only digest authority boundaries.

### Docs build reliability

`tests/test_build_docs_tooling.py`, `python scripts/build_docs.py --check-deps`,
and `python scripts/build_docs.py` cover explicit docs dependency declaration and
building through the repository docs wrapper.

### Provider invocation denial custody Phase 100-103

The Phase 100-103 custody chain is metadata-only and release-blocking for real
provider invocation:

- `docs/architecture/phase100_provider_invocation_denial_closure_execplan.md`
- `docs/architecture/phase101_provider_invocation_denial_enforcement_snapshot_execplan.md`
- `docs/architecture/phase102_provider_invocation_denial_drift_review_execplan.md`
- `docs/architecture/phase103_provider_invocation_denial_custody_checkpoint_execplan.md`
- `tests/test_phase100_provider_invocation_denial_closure.py`
- `tests/test_phase101_provider_invocation_denial_enforcement.py`
- `tests/test_phase102_provider_invocation_denial_drift_review.py`
- `tests/test_phase103_provider_invocation_denial_custody_checkpoint.py`

These artifacts prove denial custody and drift review; they do not invoke a
provider, assemble a prompt, export prompt text, construct provider clients, or
open network/runtime authority.

### Federated improvement custody runway

The current implemented modules and tests are:

- `sentientos/federation/improvement_candidate.py` / `tests/test_federated_improvement_candidate.py`
- `sentientos/federation/improvement_intake_receipt.py` / `tests/test_federated_improvement_intake_receipt.py`
- `sentientos/federation/improvement_custody_runway.py` / `tests/test_federated_improvement_custody_runway.py`
- `sentientos/federation/improvement_local_variant_artifact.py` / `tests/test_federated_improvement_local_variant_artifact.py`
- `sentientos/federation/improvement_lineage_comparison_receipt.py` / `tests/test_federated_improvement_lineage_comparison_receipt.py`
- `sentientos/federation/improvement_dissemination_receipt.py` / `tests/test_federated_improvement_dissemination_receipt.py`

These receipts and artifacts are custody/evidence/readiness surfaces only. They
do not transport, sync, adopt, execute, merge, apply, install, force updates, or
expand runtime authority.

### Real executor runtime enablement packet

`docs/architecture/real_executor_runtime_enablement_packet.md`,
`sentientos/real_executor_runtime_enablement_packet.py`,
`scripts/build_real_executor_runtime_enablement_packet.py`, and
`artifacts/proof_bundles/real_executor_runtime_enablement_packet_capability.json`
cover deterministic metadata-only runtime-enable transition requirements after
the live commit execution packet. This packet keeps real executor runtime
enablement, runtime flag flipping, executor enablement, executor invocation,
executor activation, real lock acquisition, lockfile creation, live execution,
real memory-root access, live memory write/delete/purge, index mutation, prompt
assembly, live context retrieval, action execution, external disclosure, and
external service calls disabled.

## Hard invariants currently proven

- Authority is explicit and admitted.
- Denied maintenance does not execute forge/merge ticks.
- Maintenance failure emits one structured degradation signal.
- Admission idempotency is bounded process-local TTL, not pretend-durable.
- Trust ledger recovers from state or events and degrades on malformed input.
- Suspicious federation peers are prioritized deterministically.
- Chat service import does not load the model.
- Local model custom code execution defaults false.
- Focused tests do not require broad runtime dependency install.
- Docs build dependencies are explicit.
- Provider invocation remains release-blocked.
- Federated improvement receipts do not transport, adopt, execute, merge, apply,
  install, or force updates.

## Proof commands

Run from the repository root. Expected posture for each command is successful
completion unless the local environment is missing an explicitly declared docs or
test dependency, in which case the failure should be treated as a bootstrap issue
and fixed through the documented wrapper path. Docs validation uses the
`pyproject.toml` `docs` extra and the mirrored `scripts/build_docs.py` minimal
bootstrap path; missing MkDocs is not a silent skip.

```bash
# Test-runner bootstrap and docs tooling smoke coverage.
python -m scripts.run_tests -q tests/test_run_tests_bootstrap_airlock.py tests/test_build_docs_tooling.py

# Control-plane admission and runtime closure / maintenance gating.
python -m scripts.run_tests -q tests/test_control_plane_kernel.py tests/test_sentientosd_runtime_closure.py

# Federation trust ledger recovery and probe prioritization.
python -m scripts.run_tests -q tests/test_trust_ledger.py sentientos/tests/test_trust_ledger_recovery.py

# Chat/model lazy loading and local model safety.
python -m scripts.run_tests -q tests/test_chat_service_lazy_loading.py tests/test_local_model.py tests/integration/test_chat_mistral_runtime.py

# Integration marker compatibility.
python -m scripts.run_tests -q tests/test_integration_conftest_compat.py

# Federated improvement custody/evidence runway.
python -m scripts.run_tests -q tests/test_federated_improvement_candidate.py tests/test_federated_improvement_intake_receipt.py tests/test_federated_improvement_custody_runway.py tests/test_federated_improvement_local_variant_artifact.py tests/test_federated_improvement_lineage_comparison_receipt.py tests/test_federated_improvement_dissemination_receipt.py


# Host embodiment substrate Phase 1 metadata-only proof.
python -m scripts.run_tests -q tests/test_capability_registry.py tests/test_host_inventory.py tests/test_host_resource_governor.py

# Context hygiene / prompt-boundary verification.
python scripts/verify_context_hygiene_prompt_boundaries.py

# Audit chain verification.
python scripts/verify_audits.py --strict

# Immutable manifest verification.
python scripts/audit_immutability_verifier.py --manifest vow/immutable_manifest.json

# Docs dependency check, explicit docs bootstrap, and docs build.
python scripts/build_docs.py --check-deps
python scripts/build_docs.py --bootstrap-docs
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
```

## Deferred / explicitly not implemented

- Real provider invocation.
- Prompt assembly or prompt-text export for provider invocation.
- Federation transport/sync for improvement receipts.
- Automatic adoption.
- Remote execution.
- Merge/conflict-resolution engine.
- Apply/install/update engine for federated improvement receipts.
- Production execution from rehearsal/readiness receipts.
- Durable cross-process admission idempotency.
- Cross-process trust ledger mutation locking.

## How to review

1. Read `docs/architecture/public_technical_overview.md` first.
2. Run the proof-map commands above from the repository root.
3. Inspect `tests/test_control_plane_kernel.py` and `tests/test_sentientosd_runtime_closure.py`.
4. Inspect `tests/test_trust_ledger.py` and `sentientos/tests/test_trust_ledger_recovery.py`.
5. Inspect `tests/test_chat_service_lazy_loading.py`, `tests/test_local_model.py`, and `tests/integration/test_chat_mistral_runtime.py`.
6. Inspect the federated improvement receipt tests listed in the custody runway section.
7. Build docs with `python scripts/build_docs.py --check-deps` and `python scripts/build_docs.py`.


## Host Embodiment Phase 3 policy receipts

See `docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md`. Proposal receipts are not effects. A policy decision is not authorization. PWM presence is not control authority. Phase 3 names the future Privilege Broker and Actuation Fulfillment Layer and keeps them future/deferred.


## Host Embodiment Phase 4 privilege broker eligibility

See `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`. Eligibility is not authorization. A broker receipt is not fulfillment. Fan/PWM/thermal control remains blocked/deferred. Future cooling, power, cleanup, and service actions remain behind future gates, including control-plane admission, operator/policy approval, audit, rollback, rehearsal, panic/hardware/backend/bounds gates where applicable, and the future Actuation Fulfillment Layer.

Proof command:

```bash
python -m scripts.run_tests -q tests/test_actuation_fulfillment.py tests/test_privilege_broker.py tests/test_host_resource_policy.py tests/test_capability_registry.py
```


## Host Embodiment Phase 5 actuation fulfillment scaffold

See `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md`. Phase 5 creates fulfillment rehearsal plans and receipts only. Fulfillment rehearsal is not real fulfillment. A rehearsal receipt is not an effect receipt. No host mutation occurs. Fan/PWM/thermal/power/service/cleanup actions remain blocked/deferred, and future real fulfillment still requires control-plane admission, operator/policy approval, audit receipt, rollback receipt, effect receipt, and postcondition check.

Proof command:

```bash
python -m scripts.run_tests -q tests/test_actuation_fulfillment.py tests/test_privilege_broker.py tests/test_capability_registry.py
```


## Host Embodiment Execution Proof Wing

Next proof/readiness wing: `docs/architecture/host_embodiment_execution_proof_wing.md`. Execution readiness is not authorization; the future effect receipt schema is not proof of effect; the Runtime Supervisor does not restart/kill services; real actuation remains deferred.

## Host Embodiment Authorization Review Wing

See `docs/architecture/host_embodiment_authorization_review_wing.md`. This proof surface is metadata-only review of ExecutionReadinessManifest records: authorization review is not authorization grant, a future authorization grant schema is not a real grant, real fulfillment remains deferred, and real actuation remains deferred.

## Host Embodiment Controlled Authorization + Trace Wing

- Architecture: [Host Embodiment Controlled Authorization + Trace Wing](host_embodiment_controlled_authorization_and_trace_wing.md)
- Code: `sentientos/controlled_authorization.py`, `sentientos/host_embodiment_trace.py`
- Tests: `tests/test_controlled_authorization.py`, `tests/test_host_embodiment_trace.py`

Reviewer assertions:

- Controlled authorization contract is not a live grant.
- Grant record is schema-only/future-use-only.
- Revocation record is schema-only/future-use-only.
- Authorization ledger is metadata-only and does not grant authority.
- Demo trace is reviewer proof only.
- Real fulfillment remains deferred.
- Real actuation remains deferred.

Proof path: docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md

## Host Embodiment Reviewer Demo Trace

See `docs/architecture/host_embodiment_reviewer_demo_trace.md`. Proof commands: `python scripts/build_host_embodiment_trace.py --format json`, `python scripts/build_host_embodiment_trace.py --format markdown`, and `python scripts/build_host_embodiment_trace.py --validate-only`. The demo trace is reviewer proof only; no host mutation occurs; PWM presence is not control authority; no live authorization, real effect, network, provider invocation, prompt assembly, federation transport, or remote execution occurs.

## Host Live-Grant Readiness Wing

- Architecture: [Host Live-Grant Readiness Wing](host_live_grant_readiness_wing.md) (`docs/architecture/host_live_grant_readiness_wing.md`).
- Proof: `tests/test_live_grant_readiness.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, and `tests/test_capability_registry.py`.
- Boundary: live-grant readiness is not a live grant; operator/policy approval packet is not approval; grant issue preflight does not issue a grant; real actuation remains deferred.


- Host Local Authorization Grant Wing: `docs/architecture/host_local_authorization_grant_wing.md`; proof artifact `local_authorization.json`; tests `tests/test_local_authorization_grant.py`. Local authorization grant is authority metadata, not fulfillment, and does not execute.

The [Host Fulfillment Authorization Consumption Wing](host_fulfillment_authorization_consumption_wing.md) (`docs/architecture/host_fulfillment_authorization_consumption_wing.md`) adds metadata-only fulfillment authorization request, grant consumption verification, scope match assessment, consumption receipt, and denial receipt records. Consuming authorization is not fulfillment; scope match is not execution; consumption receipts do not execute; real actuation remains deferred.

- [Host Fulfillment Executor Contract Wing](host_fulfillment_executor_contract_wing.md) (`docs/architecture/host_fulfillment_executor_contract_wing.md`): metadata-only executor contract/readiness; not an executor, not backend invocation, not dry-run execution, not control-plane admission, and not actuation.


See also: [Host Dry-Run Execution Harness Wing](host_dry_run_execution_harness_wing.md) (`docs/architecture/host_dry_run_execution_harness_wing.md`), which is simulation-only; dry-run execution is not real fulfillment, dry-run result is not an effect receipt, dry-run receipt is not proof of host mutation, and real actuation remains deferred.

See also: [Host Dry-Run Effect Verification / Audit Closure Wing](host_dry_run_audit_closure_wing.md) (`docs/architecture/host_dry_run_audit_closure_wing.md`). Dry-run effect verification is not a real effect receipt; dry-run postcondition verification is not real host postcondition check; dry-run rollback rehearsal is not real rollback; dry-run audit closure is not production audit receipt; real actuation remains deferred.


## Real effect capability admission link

See [Host Real Effect Capability Admission Wing](host_real_effect_capability_admission_wing.md) (`docs/architecture/host_real_effect_capability_admission_wing.md`): dry-run closure does not automatically permit real effects; real effect admission is not implementation, the admission decision does not authorize implementation or execution, the plan scaffold does not start implementation, cooling/hardware control remains blocked by default, and real actuation remains deferred.

- [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md) — first intentionally real effect, explicit diagnostic artifact write only, reviewer bundle does not run it by default.

The exact-artifact rollback proof is documented in [Host Local Diagnostic Exact Artifact Rollback Pilot Wing](host_local_diagnostic_exact_rollback_pilot_wing.md): it is the first real rollback and is exact diagnostic artifact only, not general cleanup.

See also: [Host Steward / Delegated Runner Boundary Wing](host_steward_delegated_runner_boundary_wing.md) (`docs/architecture/host_steward_delegated_runner_boundary_wing.md`) for the next authority boundary after the local effect transaction ledger. It models broad top-level host-steward authority without granting delegated runners ambient authority.

## Built-In Local Effect Runner Pilot

- Architecture: `docs/architecture/host_builtin_local_effect_runner_pilot_wing.md`.
- This is the first actual delegated runner implementation.
- It is in-process only.
- It supports only local diagnostic artifact write and exact artifact rollback.
- It uses no subprocess/shell/network/provider/prompt.
- It is not a general runner framework.
- It does not broaden cleanup/hardware/service/power/fan/thermal control.
- Proof command listed but not run by default: `python scripts/run_builtin_local_effect_runner.py --action local_diagnostic_artifact_write --output-dir /tmp/sentientos-local-effect-runner --summary`.

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.

## Host Workspace-Scoped File Effect Pilot Wing

- Doc: `docs/architecture/host_workspace_file_effect_pilot_wing.md`
- API: `sentientos/workspace_file_effect.py`
- CLI: `scripts/run_workspace_file_effect.py`
- Tests: `tests/test_workspace_file_effect.py`, `tests/test_run_workspace_file_effect_script.py`
- Proof bundle artifact: `workspace_file_effect_capability.json`

This pilot creates or updates exactly one explicit file inside an explicit workspace root. It is not general filesystem access. It is not cleanup. It captures preimage for replacements, verifies exact-target postconditions, supports exact-target rollback only, and refuses recursive delete, wildcard delete, unrelated file delete, symlink targets, directory targets, path traversal, and absolute targets. It uses no subprocess/shell/network/provider/prompt path and does not touch hardware, services, power, fan/PWM, or thermal controls. The reviewer proof bundle documents it but does not run it by default.

See also: [Host Workspace File Runner / Transaction Integration Wing](host_workspace_file_runner_transaction_wing.md).

- Workspace file transaction orchestrator: see [Host Workspace File Transaction Orchestrator Wing](host_workspace_file_transaction_orchestrator_wing.md) for implemented single-target workspace update/rollback/ledger modes; the previous orchestration deferral is removed without adding general filesystem, cleanup, subprocess, shell, network, provider, prompt, or hardware/service/power/fan/thermal authority.

## Next workspace planning wing

Workspace change-set admission is documented in [Host Workspace Change Set Admission Controller](host_workspace_change_set_admission_wing.md) (`docs/architecture/host_workspace_change_set_admission_wing.md`): it is a bounded metadata-only eligibility gate before preflight, inspects supplied proposal metadata only, may write one caller-supplied admission artifact, and does not read workspace target files, check filesystem existence, compute filesystem digests, preflight, plan transactions, execute, rollback, verify replay, close lifecycle state, cleanup, schedule, or invoke subprocess/shell/network/provider/prompt/hardware/service/power/fan/thermal paths.

See [`Host Workspace Change Set Preflight / Planning Wing`](host_workspace_change_set_preflight_wing.md) (`docs/architecture/host_workspace_change_set_preflight_wing.md`) for the metadata-only layer that prepares bounded multi-target workspace changes but does not execute them, reads only explicitly declared target metadata/digests, performs no target writes, performs no rollback, invokes no runner/orchestrator, and is followed by bounded change-set transaction execution in the execution pilot wing.


The [Host Workspace Change Set Transaction Execution Pilot Wing](host_workspace_change_set_execution_wing.md) (`docs/architecture/host_workspace_change_set_execution_wing.md`) adds the first bounded multi-target workspace execution layer after preflight/planning. It consumes passed preflight/transaction plans, uses existing single-target helpers, records partial state visibly, and the reviewer proof bundle documents but does not run it by default.


The [Host Workspace Change Set Execution Verification / Replay Audit Wing](host_workspace_change_set_execution_verification_wing.md) (`docs/architecture/host_workspace_change_set_execution_verification_wing.md`) adds a read-only replay-audit layer for completed change-set executions. It reads only declared manifest targets, checks receipt/ledger/closure and optional rollback evidence, may write one caller-supplied verification artifact, and does not execute, rollback, cleanup, schedule, scan undeclared files, or invoke subprocess/shell/network/provider/prompt/hardware/service/power/fan/thermal paths.


Workspace change-set lifecycle closure is documented in [Host Workspace Change Set Lifecycle Closure Manifest Wing](host_workspace_change_set_lifecycle_closure_wing.md) (`docs/architecture/host_workspace_change_set_lifecycle_closure_wing.md`): it is a metadata-only sealing layer after verification that consumes supplied evidence JSON only, emits compact lifecycle closure statuses, may write one caller-supplied closure artifact, and does not read target files, recompute target filesystem digests, execute, rollback, verify replay, cleanup, schedule, recurse directories, expand wildcards, or invoke subprocess/shell/network/provider/prompt/hardware/service/power/fan/thermal paths.

The [Host Workspace Change Set Lifecycle Orchestration Wing](host_workspace_change_set_lifecycle_orchestration_wing.md) (`docs/architecture/host_workspace_change_set_lifecycle_orchestration_wing.md`) adds explicit bounded lifecycle coordination across admission, preflight/planning, optional execution, optional verification, and optional closure. It delegates to the existing wings only, supports dry-run admission plus preflight without target execution, may write only caller-supplied stage/orchestration artifacts, and does not add file-effect primitives, direct target reads, target digest recomputation, cleanup, scheduling, subprocess/shell/network/provider/prompt paths, or new autonomy loops.

- [Task Work Item Intake Adapter Wing](task_work_item_intake_adapter_wing.md)

### Work item lifecycle dry-run closure manifest

`sentientos/work_item_dry_run_closure.py`, `scripts/build_work_item_dry_run_closure.py`, `tests/test_work_item_dry_run_closure.py`, and `tests/test_build_work_item_dry_run_closure_script.py` provide deterministic metadata-only closure manifest sealing for supplied packet/handoff/dry-run evidence. This wing does not invoke intake/handoff/dry-run/lifecycle helpers and does not execute workspace effects.

See `docs/architecture/task_work_item_lifecycle_dry_run_closure_wing.md`.

### Work item dry-run review packet orchestration

`sentientos/work_item_review_packet.py` and `scripts/build_work_item_review_packet.py` orchestrate metadata-only intake → handoff → eligible dry-run adapter → optional dry-run closure into a compact reviewer-facing packet with deterministic operator-action mapping. This wing does not execute workspace effects, agents, scheduler paths, issue/PR/branch mutation, network/provider/prompt paths, or full lifecycle execution modes.

See `docs/architecture/task_work_item_dry_run_review_packet_orchestration_wing.md`.

`sentientos/work_item_promotion_gate.py` and `scripts/evaluate_work_item_promotion.py` evaluate completed dry-run review packets into deterministic promotion dossiers that remain metadata-readiness only and never execute workspace change-set lifecycle helpers. The reviewer proof bundle includes `work_item_promotion_gate_capability.json` with `proof_command_not_run` by default.

See `docs/architecture/task_work_item_promotion_gate_wing.md`.


See `docs/architecture/task_work_item_operator_admission_review_wing.md`.


See `docs/architecture/task_work_item_operator_confirmed_admission_run_wing.md`.


See `docs/architecture/task_work_item_operator_confirmed_preflight_run_wing.md`.

See `docs/architecture/task_work_item_operator_execution_review_wing.md`.

See `docs/architecture/task_work_item_operator_lifecycle_closure_review_wing.md`.

- [Operator Confirmed Execution Run Wing](task_work_item_operator_confirmed_execution_run_wing.md)
- [Operator Confirmed Verification Run Wing](task_work_item_operator_confirmed_verification_run_wing.md)
- [Operator Lifecycle Closure Review Wing](task_work_item_operator_lifecycle_closure_review_wing.md)

- docs/architecture/task_work_item_operator_confirmed_lifecycle_closure_run_wing.md

`sentientos/work_item_lifecycle_completion_dossier.py`, `scripts/build_work_item_lifecycle_completion_dossier.py`, `tests/test_work_item_lifecycle_completion_dossier.py`, and `tests/test_build_work_item_lifecycle_completion_dossier_script.py` provide deterministic metadata-only lifecycle completion dossier generation from closure-run evidence and optional supporting chain packets.

See `docs/architecture/task_work_item_lifecycle_completion_dossier_wing.md`.


### Work Item Lifecycle Completion Verifier

`sentientos/work_item_lifecycle_completion_verifier.py` and `scripts/verify_work_item_lifecycle_completion_dossier.py` provide deterministic metadata-only lifecycle completion dossier verification with optional supplied-stage digest/status/work-item alignment checks and explicit non-authority boundaries.

See `docs/architecture/task_work_item_lifecycle_completion_verifier_wing.md`.

### Work Item Lifecycle Final Attestation

`sentientos/work_item_lifecycle_final_attestation.py` and `scripts/build_work_item_lifecycle_final_attestation.py` provide deterministic metadata-only final attestation bundle generation from lifecycle completion dossier + completion verification report evidence.

See `docs/architecture/task_work_item_lifecycle_final_attestation_wing.md`.



### Work Item Lifecycle Attestation Index

`sentientos/work_item_lifecycle_attestation_index.py` and `scripts/build_work_item_lifecycle_attestation_index.py` provide deterministic metadata-only indexing of lifecycle final attestation bundles.

See `docs/architecture/task_work_item_lifecycle_attestation_index_wing.md`.


Work item lifecycle attestation review digest verification is documented in `docs/architecture/task_work_item_lifecycle_attestation_review_digest_verifier_wing.md` with metadata-verification-only boundaries.


Work item lifecycle attestation review digest indexing is documented in `docs/architecture/task_work_item_lifecycle_attestation_review_digest_index_wing.md` with metadata-only digest-index boundaries.

Work item lifecycle attestation review digest index verification is documented in `docs/architecture/task_work_item_lifecycle_attestation_review_digest_index_verifier_wing.md` with metadata-only verification boundaries.


- Household presence layer doctrine: `docs/architecture/household_presence_layer.md`
- Household presence camera event bridge: `docs/architecture/household_presence_camera_event_bridge.md`
- Household presence deadzone redaction contract: `docs/architecture/household_presence_deadzone_redaction.md`
- Household presence camera redaction pipeline: `docs/architecture/household_presence_camera_redaction_pipeline.md`
- Household presence camera policy chain: `docs/architecture/household_presence_camera_policy_chain.md`
- Household presence camera dry-run adapter: `docs/architecture/household_presence_camera_dry_run_adapter.md`
- Household presence camera local adapter shell: `docs/architecture/household_presence_camera_local_adapter_shell.md`
- Household presence camera live adapter stub: `docs/architecture/household_presence_camera_live_adapter_stub.md`
- Household presence camera disabled-capture adapter: `docs/architecture/household_presence_camera_disabled_capture_adapter.md`
- Household presence camera capture-authorization envelope: `docs/architecture/household_presence_camera_capture_authorization.md`
- Household presence camera capture review packet: `docs/architecture/household_presence_camera_capture_review_packet.md`
- Household presence camera capture review decision ledger: `docs/architecture/household_presence_camera_capture_review_decision_ledger.md`
- Household presence camera operator review trend ledger: `docs/architecture/household_presence_camera_operator_review_trend_ledger.md`
- Household presence camera operator grant renewal request packet: `docs/architecture/household_presence_camera_operator_grant_renewal_request_packet.md`
- Household presence camera dry-run continuation gate: `docs/architecture/household_presence_camera_dry_run_continuation_gate.md`
- Household presence camera future live-candidate deferral registry: `docs/architecture/household_presence_camera_future_live_deferral_registry.md`
- Household presence camera review chain summary packet: `docs/architecture/household_presence_camera_review_chain_summary_packet.md`

- docs/development/codex_landing_supervisor.md


### Household presence camera zone configuration

See `docs/architecture/household_presence_camera_zone_config.md` for metadata-only zone taxonomy, precedence, staleness review, and compatibility mapping to deadzone/redaction policy surfaces.

- Household presence camera host inventory bridge: `docs/architecture/household_presence_camera_host_inventory_bridge.md`
- Household presence camera capture denial ledger: `docs/architecture/household_presence_camera_capture_denial_ledger.md`
- Live commit safety interlock: `docs/architecture/live_commit_safety_interlock.md`
- Real live memory commit adapter readiness envelope: `docs/architecture/real_live_memory_commit_adapter_readiness_envelope.md`
- Explicit live memory runtime execution gate: `docs/architecture/explicit_live_memory_runtime_execution_gate.md`
- Real live memory commit executor plan packet: `docs/architecture/real_live_memory_commit_executor_plan_packet.md`
- Live executor lock lease gate: `docs/architecture/live_executor_lock_lease_gate.md`
- Live executor preflight packet: `docs/architecture/live_executor_preflight_packet.md`
- Live executor activation record: `docs/architecture/live_executor_activation_record.md`
- Live executor invocation harness: `docs/architecture/live_executor_invocation_harness.md`
- Real live memory commit executor implementation skeleton: `docs/architecture/real_live_memory_commit_executor_implementation_skeleton.md`
- Real live memory commit executor enablement gate: `docs/architecture/real_live_memory_commit_executor_enablement_gate.md`
- Constrained executor enablement path packet: `docs/architecture/constrained_executor_enablement_path_packet.md`
- Future live memory commit execution gate: `docs/architecture/future_live_memory_commit_execution_gate.md`
- Live commit execution packet: `docs/architecture/live_commit_execution_packet.md`

Runtime gate reviewers should also inspect `docs/architecture/real_executor_runtime_gate.md`, `sentientos/real_executor_runtime_gate.py`, `scripts/build_real_executor_runtime_gate.py`, and `artifacts/proof_bundles/real_executor_runtime_gate_capability.json` to confirm the gate remains metadata-only and disabled.

Guarded executor path reviewers should also inspect `docs/architecture/guarded_executor_path_packet.md`, `sentientos/guarded_executor_path_packet.py`, `scripts/build_guarded_executor_path_packet.py`, and `artifacts/proof_bundles/guarded_executor_path_packet_capability.json` to confirm the packet remains metadata-only and disabled.

### Guarded executor invocation packet

`sentientos/guarded_executor_invocation_packet.py`, `scripts/build_guarded_executor_invocation_packet.py`, `tests/test_guarded_executor_invocation_packet.py`, and `tests/test_build_guarded_executor_invocation_packet_script.py` add the [Guarded Executor Invocation Packet](guarded_executor_invocation_packet.md). It verifies guarded executor path, runtime gate, runtime enablement, live execution packet, and downstream executor evidence digests and decisions while remaining metadata-only, default-deny, non-mutating, non-executing, non-authoritative, disabled, and forbidden from touching real memory roots.

`sentientos/real_executor_invocation_gate.py`, `scripts/build_real_executor_invocation_gate.py`, `tests/test_real_executor_invocation_gate.py`, and `tests/test_build_real_executor_invocation_gate_script.py` add the [Real Executor Invocation Gate](real_executor_invocation_gate.md). It verifies guarded executor invocation packet evidence plus downstream runtime, enablement, live execution, lock, activation, preflight, plan, final review, real-root admission, and sandbox evidence digests and decisions while remaining metadata-only, default-deny, disabled, non-authoritative, non-executing, and forbidden from touching real memory roots.

`sentientos/real_executor_run_packet.py`, `scripts/build_real_executor_run_packet.py`, `tests/test_real_executor_run_packet.py`, and `tests/test_build_real_executor_run_packet_script.py` add the [Real Executor Run Packet](real_executor_run_packet.md). It verifies real executor invocation gate evidence plus guarded invocation, runtime, enablement, live execution, lock, activation, preflight, plan, final review, real-root admission, and sandbox evidence digests and decisions while remaining metadata-only, default-deny, disabled, non-authoritative, non-executing, and forbidden from touching real memory roots.

`sentientos/real_executor_run_gate.py`, `scripts/build_real_executor_run_gate.py`, `tests/test_real_executor_run_gate.py`, and `tests/test_build_real_executor_run_gate_script.py` add the [Real Executor Run Gate](real_executor_run_gate.md). It verifies real executor run packet evidence plus invocation gate, guarded invocation, guarded path, runtime, enablement, live execution, lock, activation, preflight, plan, final review, real-root admission, and sandbox evidence digests and decisions while remaining metadata-only, default-deny, disabled, non-authoritative, non-executing, and forbidden from touching real memory roots.
`sentientos/real_executor_execution_plan.py`, `scripts/build_real_executor_execution_plan.py`, `tests/test_real_executor_execution_plan.py`, and `tests/test_build_real_executor_execution_plan_script.py` add the [Real Executor Execution Plan](real_executor_execution_plan.md). It verifies real executor run gate evidence plus run packet, invocation gate, guarded invocation, guarded path, runtime, enablement, live execution, lock, activation, preflight, plan, final review, real-root admission, and sandbox evidence digests and decisions while remaining metadata-only, default-deny, disabled, non-authoritative, non-executing, and forbidden from touching real memory roots.

`sentientos/real_executor_execution_gate.py`, `scripts/build_real_executor_execution_gate.py`, `tests/test_real_executor_execution_gate.py`, and `tests/test_build_real_executor_execution_gate_script.py` add the [Real Executor Execution Gate](real_executor_execution_gate.md). It verifies real executor execution plan evidence plus carried-through run gate, run packet, invocation gate, guarded invocation, guarded path, runtime, enablement, live execution, lock, activation, preflight, plan, final review, real-root admission, and sandbox evidence digests and decisions while remaining metadata-only, default-deny, disabled, non-authoritative, non-executing, and forbidden from touching real memory roots.

`sentientos/real_executor_execution_authorization_packet.py`, `scripts/build_real_executor_execution_authorization_packet.py`, `tests/test_real_executor_execution_authorization_packet.py`, and `tests/test_build_real_executor_execution_authorization_packet_script.py` add the [Real Executor Execution Authorization Packet](real_executor_execution_authorization_packet.md). It verifies real executor execution gate evidence plus carried-through run gate, run packet, invocation gate, guarded invocation, guarded path, runtime, enablement, live execution, lock, activation, preflight, plan, final review, real-root admission, and sandbox evidence digests and decisions while remaining metadata-only, default-deny, disabled, non-authoritative, non-executing, not authorization, not permission to execute, and forbidden from touching real memory roots.

`sentientos/real_executor_execution_authorization_gate.py`, `scripts/build_real_executor_execution_authorization_gate.py`, `tests/test_real_executor_execution_authorization_gate.py`, and `tests/test_build_real_executor_execution_authorization_gate_script.py` add the [Real Executor Execution Authorization Gate](real_executor_execution_authorization_gate.md). It verifies real executor execution authorization packet evidence plus carried-through execution gate, execution plan, run gate, run packet, invocation gate, guarded invocation, guarded path, runtime, enablement, live execution, lock, activation, preflight, plan, final review, real-root admission, and sandbox evidence digests and decisions while remaining metadata-only, default-deny, disabled, non-authoritative, non-executing, not authorization, not permission to execute, and forbidden from touching real memory roots.

`sentientos/real_executor_execution_permit_packet.py`, `scripts/build_real_executor_execution_permit_packet.py`, `tests/test_real_executor_execution_permit_packet.py`, and `tests/test_build_real_executor_execution_permit_packet_script.py` add the [Real Executor Execution Permit Packet](real_executor_execution_permit_packet.md). It verifies real executor execution authorization gate evidence plus carried-through authorization packet, execution gate, execution plan, run gate, run packet, invocation gate, guarded invocation, guarded path, runtime, enablement, live execution, lock, activation, preflight, plan, final review, real-root admission, and sandbox evidence digests and decisions while remaining metadata-only, default-deny, disabled, non-authoritative, non-executing, not a permit, not permit issuance, not authorization, not permission to execute, and forbidden from touching real memory roots.

- Real live memory commit execution gate: `docs/architecture/real_live_memory_commit_execution_gate.md`
- Real live memory commit execution packet: `docs/architecture/real_live_memory_commit_execution_packet.md`
- Real live memory commit adapter admission gate: `docs/architecture/real_live_memory_commit_adapter_admission_gate.md`
- Real live memory commit adapter admission packet: `docs/architecture/real_live_memory_commit_adapter_admission_packet.md`
