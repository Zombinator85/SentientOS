# Host Steward / Delegated Runner Boundary Wing

This wing follows the [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md). The local effect transaction ledger added integrity over the first local diagnostic effect and exact-artifact rollback lifecycle, but did not add a new host effect. This wing adds the next authority model: the boundary between broad top-level local host-steward authority and narrow delegated-runner authority.

## Purpose

SentientOS is intended to become a full local host stewardship runtime: a user-space runtime that can eventually operate the machine under explicit operator authority. The core host steward may eventually hold broad operator-delegated local authority.

That broad host-steward authority is not inherited by every child action, generated script, plugin, backend adapter, federation artifact, external tool, or future runner. Delegated runners do not inherit ambient authority by default. Generated code, plugins, backend adapters, federation imports, and external tools must receive typed, scoped, revocable, auditable grants before any future effect path may consume authority.

## What this wing implements

`sentientos/host_steward_boundary.py` defines metadata-only records for:

- `HostStewardAuthorityProfile`
- `DelegatedRunnerBoundaryProfile`
- `ExecutionContainmentProfile`
- `BackendAdapterAuthorityDeclaration`
- `RunnerCapabilityGrantScaffold`
- `RunnerBoundaryAssessment`
- `RunnerBoundaryViolationReceipt`

These records are authority models and proof surfaces only. They are not runners, not execution permissions, not backend implementations, and not host effects.

## Boundary rules

- A host steward profile may state that the top-level SentientOS steward can eventually hold broad local operator-delegated authority.
- Delegated runner boundary profiles explicitly deny ambient authority inheritance.
- Execution containment profiles are declarations, not live sandbox execution.
- Backend adapter declarations do not load or invoke backends.
- Runner capability grant scaffolds do not issue live grants.
- Runner boundary assessments do not authorize runner execution.
- Runner boundary violation receipts record a blocked posture; they do not execute or mutate anything.

## Current real-effect posture

This wing does not spawn processes, use shell, use network, invoke providers, assemble prompts, mutate host state, call control-plane execution, or broaden current real effects.

The current only real effects remain:

1. the explicit local diagnostic artifact write; and
2. the explicit exact-artifact rollback for that diagnostic artifact.

Hardware control, service control, power control, cleanup, network egress, provider invocation, prompt assembly/export, subprocess execution, shell execution, fan/PWM writes, thermal actuation, OS backend invocation, federation transport/sync/adoption, remote execution, and uncontrolled runtime authority expansion remain blocked or deferred.

## Reviewer proof bundle

The reviewer proof bundle includes `host_steward_boundary.json`. It proves that:

- delegated runners do not inherit ambient authority;
- no runner executes by default;
- containment profiles are not live sandbox execution;
- backend declarations do not load or invoke backends;
- grant scaffolds do not issue live runner grants; and
- boundary assessments do not authorize runner execution.

Bundle generation remains metadata-only and does not run the diagnostic effect, rollback, ledger builder, runner, backend, network, provider, prompt, shell, or subprocess path.

## Capability registry posture

The capability registry marks host-steward boundary surfaces as implemented metadata-only records:

- `host_steward_authority_profile` is authority-profile-only.
- `delegated_runner_boundary_profile` is boundary-profile-only.
- `execution_containment_profile` is containment-profile-only.
- `backend_adapter_authority_declaration` is declaration-only.
- `runner_capability_grant_scaffold` is scaffold-only.
- `runner_boundary_assessment` is assessment-only.
- `runner_boundary_violation_receipt` is receipt-only.

`live_runner_execution` remains deferred. Subprocess, shell, network, provider, prompt assembly, hardware control, service control, power control, cleanup, fan/PWM, and thermal runners remain blocked or deferred.

## Implementation links

- Module: `sentientos/host_steward_boundary.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_host_steward_boundary.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`

## Bounded Built-In Runner Pilot

See `docs/architecture/host_builtin_local_effect_runner_pilot_wing.md` for the first actual delegated runner implementation. It remains in-process only, supports only local diagnostic artifact write and exact-artifact rollback, and is not a general runner framework.

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.
