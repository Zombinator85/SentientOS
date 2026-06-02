# Reviewer First-Run Proof Bundle

The bundle now includes `safety_gates.json`; see the [Host Actuation Safety Gate Wing](host_actuation_safety_gate_wing.md) (`docs/architecture/host_actuation_safety_gate_wing.md`) for the metadata-only safety gate posture. Safety gates are not authorization.
This doc is the first practical reviewer command path after reading the [public technical overview](public_technical_overview.md). It packages the current deterministic, non-mutating host-embodiment proof chain into one local output directory so a serious reviewer can run one safe command, inspect the story, and archive the artifacts.

## Boundary

The reviewer proof bundle is metadata/export-only. It packages the deterministic non-mutating host-embodiment trace and the capability/deferred-action posture.

By default, the bundle uses fake/sample thermal+PWM telemetry. It does not collect live host data by default, does not grant authorization, does not perform effects, does not mutate host state, does not perform fan/PWM writes, does not perform thermal writes, does not mutate power profiles, does not restart services, does not clean up or delete files, does not perform network egress, does not invoke providers, does not assemble/export prompts, does not transport/sync/adopt federation state, and does not perform remote execution.

The command writes only explicit local bundle files under the caller-supplied output directory.

## Run the first proof bundle

From the repository root:

```bash
python scripts/build_reviewer_proof_bundle.py --output-dir /tmp/sentientos-reviewer-proof
python scripts/build_reviewer_proof_bundle.py --output-dir /tmp/sentientos-reviewer-proof --force
python scripts/build_reviewer_proof_bundle.py --output-dir /tmp/sentientos-reviewer-proof --summary
```

`--force` overwrites only the known bundle files inside the explicit output directory. It does not delete unrelated files.

`--verify` is intentionally unsupported in this packaging pass. The default command lists bounded local proof commands in `proof_commands.json` with `proof_command_not_run`; reviewers can run those commands separately when they want to verify the chain.

## Generated files

The bundle writes:

- `trace.json` — deterministic sorted-key trace JSON.
- `trace.md` — reviewer-readable Markdown trace.
- `trace.summary.txt` — compact summary of the non-mutating proof posture.
- `capability_registry_summary.json` — metadata-only capability registry summary and records.
- `deferred_actions.json` — deferred/blocked action inventory.
- `safety_gates.json` — metadata-only host actuation safety gate posture; safety gates are not authorization.
- `live_grant_readiness.json` — readiness/preflight-only live-grant posture; it is not a live grant.
- `local_authorization.json` — local authorization-record posture; it is not fulfillment.
- `fulfillment_authorization.json` — authorization consumption posture; consuming authorization is not fulfillment.
- `executor_contract.json` — executor contract/readiness posture; executor contract is not an executor.
- `dry_run_execution.json` — simulation-only dry-run harness posture; dry-run execution is not real fulfillment or an effect receipt.
- `proof_commands.json` — proof command manifest; commands are listed but not run by default.
- `README.md` — local reviewer guide for the bundle directory.
- `bundle_manifest.json` — manifest, artifact digests, command records, and safety flags.

## Inspect first

Reviewers should inspect these files in order:

1. `README.md`
2. `trace.md`
3. `bundle_manifest.json`
4. `deferred_actions.json`
5. `safety_gates.json`
6. `live_grant_readiness.json`
7. `local_authorization.json`
8. `fulfillment_authorization.json`
9. `executor_contract.json`
10. `dry_run_execution.json`
11. `proof_commands.json`

## What the bundle proves

The bundle exposes the same non-mutating ladder as the host embodiment trace:

collector results → inventory → telemetry → pressure → policy → proposal → broker eligibility → broker review → fulfillment rehearsal → execution proof → authorization review → controlled authorization contract → schema-only grant/revocation records → metadata-only ledger → reviewer trace.

The reviewer should see that:

- PWM presence is telemetry, not control authority.
- The controlled authorization contract is not a live grant.
- Safety gates are metadata-only prerequisites, not authorization or fulfillment.
- Grant/revocation records are schema-only/future-use-only.
- Real effect execution and rollback execution remain deferred.
- Real fan/PWM control, thermal actuation, power mutation, service restart, cleanup, provider invocation, prompt export, federation transport/sync/adoption, and remote execution remain deferred or blocked.
- The proof command manifest is inventory by default, not execution.

## Implementation links

- Bundle module: `sentientos/reviewer_proof_bundle.py`
- Bundle CLI: `scripts/build_reviewer_proof_bundle.py`
- Trace builder: `sentientos/host_embodiment_trace.py`
- Trace export: `sentientos/host_embodiment_trace_export.py`
- Capability registry: `sentientos/capability_registry.py`
- Tests: `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`

## Live-grant readiness artifact

The bundle includes `live_grant_readiness.json`, documented in [Host Live-Grant Readiness Wing](host_live_grant_readiness_wing.md) (`docs/architecture/host_live_grant_readiness_wing.md`). The artifact is metadata-only reviewer proof: live-grant readiness is not a live grant, the operator/policy approval packet is not approval, and the grant issue preflight receipt does not issue a grant.

The bundle also includes `local_authorization.json` for the [Host Local Authorization Grant Wing](host_local_authorization_grant_wing.md); this is authority metadata only and does not authorize fulfillment.

Path link: `docs/architecture/host_local_authorization_grant_wing.md`.

The bundle also writes `fulfillment_authorization.json` for the [Host Fulfillment Authorization Consumption Wing](host_fulfillment_authorization_consumption_wing.md). The artifact states that consuming authorization is not fulfillment, scope match is not execution, and no effect or host mutation is performed.

Path: `docs/architecture/host_fulfillment_authorization_consumption_wing.md`.

The bundle also includes `executor_contract.json` for the [Host Fulfillment Executor Contract Wing](host_fulfillment_executor_contract_wing.md): executor contract is not an executor, backend declaration does not load/invoke backend, dry-run plan is not dry-run execution, admission packet is not control-plane admission, and real actuation remains deferred.

Proof path: `docs/architecture/host_fulfillment_executor_contract_wing.md`.

The bundle also includes `dry_run_execution.json` for the [Host Dry-Run Execution Harness Wing](host_dry_run_execution_harness_wing.md): the harness uses only inert simulated backends; dry-run execution is not real fulfillment; a dry-run result is not an effect receipt; a dry-run receipt is not proof of host mutation; real actuation remains deferred.

Proof path: `docs/architecture/host_dry_run_execution_harness_wing.md`.


See also: [Host Dry-Run Execution Harness Wing](host_dry_run_execution_harness_wing.md) (`docs/architecture/host_dry_run_execution_harness_wing.md`), which is simulation-only; dry-run execution is not real fulfillment, dry-run result is not an effect receipt, dry-run receipt is not proof of host mutation, and real actuation remains deferred.

The bundle also includes `dry_run_audit_closure.json`; see [Host Dry-Run Effect Verification / Audit Closure Wing](host_dry_run_audit_closure_wing.md). Dry-run audit closure verifies dry-run evidence only and is not a real effect receipt, not a real host postcondition check, not real rollback, and not a production audit receipt.

Proof path: docs/architecture/host_dry_run_audit_closure_wing.md


## Real effect capability admission link

See [Host Real Effect Capability Admission Wing](host_real_effect_capability_admission_wing.md) (`docs/architecture/host_real_effect_capability_admission_wing.md`): dry-run closure does not automatically permit real effects; real effect admission is not implementation, the admission decision does not authorize implementation or execution, the plan scaffold does not start implementation, cooling/hardware control remains blocked by default, and real actuation remains deferred.

The bundle documents but does not run the [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md); its optional CLI command is listed as not run by default.

The proof bundle lists, but does not run, the exact-artifact rollback CLI documented in [Host Local Diagnostic Exact Artifact Rollback Pilot Wing](host_local_diagnostic_exact_rollback_pilot_wing.md).

The bundle also includes `local_effect_transaction_ledger_capability.json`; its ledger command is listed as `proof_command_not_run` and does not run effect or rollback by default. See [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md).

See also: [Host Steward / Delegated Runner Boundary Wing](host_steward_delegated_runner_boundary_wing.md) (`docs/architecture/host_steward_delegated_runner_boundary_wing.md`) for the next authority boundary after the local effect transaction ledger. It models broad top-level host-steward authority without granting delegated runners ambient authority.

## Built-In Local Effect Runner Proof Artifact

The proof bundle includes `builtin_local_effect_runner_capability.json` for `docs/architecture/host_builtin_local_effect_runner_pilot_wing.md`. The proof bundle does not invoke the runner by default; listed runner commands remain `proof_command_not_run`.

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.

## Workspace file effect capability artifact

The proof bundle includes `workspace_file_effect_capability.json` for the [Host Workspace-Scoped File Effect Pilot Wing](host_workspace_file_effect_pilot_wing.md). The bundle lists `python scripts/run_workspace_file_effect.py --workspace-root /tmp/sentientos-workspace-file-effect --target demo.txt --payload "hello" --summary` as `proof_command_not_run` and does not run the workspace file effect by default. The capability is explicit command/API only, supports exactly one workspace-scoped file target, captures preimage, supports exact rollback, and does not perform recursive/wildcard/unrelated delete, subprocess/shell/network/provider/prompt, hardware/service/power, or general cleanup.

See also: [Host Workspace File Runner / Transaction Integration Wing](host_workspace_file_runner_transaction_wing.md).

- Workspace file transaction orchestrator: see [Host Workspace File Transaction Orchestrator Wing](host_workspace_file_transaction_orchestrator_wing.md) for implemented single-target workspace update/rollback/ledger modes; the previous orchestration deferral is removed without adding general filesystem, cleanup, subprocess, shell, network, provider, prompt, or hardware/service/power/fan/thermal authority.

## Next workspace planning wing

See [`Host Workspace Change Set Preflight / Planning Wing`](host_workspace_change_set_preflight_wing.md) (`docs/architecture/host_workspace_change_set_preflight_wing.md`) for the metadata-only layer that prepares bounded multi-target workspace changes but does not execute them, reads only explicitly declared target metadata/digests, performs no target writes, performs no rollback, invokes no runner/orchestrator, and is followed by the bounded change-set transaction execution pilot wing.

## Workspace change-set execution proof artifact

The bundle includes `workspace_change_set_execution_capability.json` for [Host Workspace Change Set Transaction Execution Pilot Wing](host_workspace_change_set_execution_wing.md). It documents the bounded capability but does not run execution by default.


The [Host Workspace Change Set Execution Verification / Replay Audit Wing](host_workspace_change_set_execution_verification_wing.md) (`docs/architecture/host_workspace_change_set_execution_verification_wing.md`) adds a read-only replay-audit layer for completed change-set executions. It reads only declared manifest targets, checks receipt/ledger/closure and optional rollback evidence, may write one caller-supplied verification artifact, and does not execute, rollback, cleanup, schedule, scan undeclared files, or invoke subprocess/shell/network/provider/prompt/hardware/service/power/fan/thermal paths.


Workspace change-set lifecycle closure is documented in [Host Workspace Change Set Lifecycle Closure Manifest Wing](host_workspace_change_set_lifecycle_closure_wing.md) (`docs/architecture/host_workspace_change_set_lifecycle_closure_wing.md`): it is a metadata-only sealing layer after verification that consumes supplied evidence JSON only, emits compact lifecycle closure statuses, may write one caller-supplied closure artifact, and does not read target files, recompute target filesystem digests, execute, rollback, verify replay, cleanup, schedule, recurse directories, expand wildcards, or invoke subprocess/shell/network/provider/prompt/hardware/service/power/fan/thermal paths.

The [Host Workspace Change Set Lifecycle Orchestration Wing](host_workspace_change_set_lifecycle_orchestration_wing.md) (`docs/architecture/host_workspace_change_set_lifecycle_orchestration_wing.md`) coordinates the existing admission, preflight/planning, optional execution, optional verification, and optional closure wings without adding target-file primitives, direct target reads, target digest recomputation, cleanup, scheduling, external tools, or provider/prompt authority.

The proof bundle includes `real_live_memory_commit_executor_enablement_gate_capability.json` for the [Real Live Memory Commit Executor Enablement Gate](real_live_memory_commit_executor_enablement_gate.md). The artifact is metadata-only and records that the gate does not enable, invoke, activate, lock, write, delete, purge, index, assemble prompts, retrieve live context, execute actions, disclose externally, or grant authority.

The proof bundle includes `future_live_memory_commit_execution_gate_capability.json` for the [Future Live Memory Commit Execution Gate](future_live_memory_commit_execution_gate.md). The artifact is metadata-only and records that the gate does not execute live commits, enable, invoke, or activate an executor, acquire locks, create lockfiles, touch real memory roots, write, delete, purge, index, assemble prompts, retrieve live context, execute actions, disclose externally, or grant authority.
