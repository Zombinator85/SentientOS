# Host Privilege Review and Fulfillment Rehearsal Runtime

`sentientos/host_privilege_review_runtime.py` closes the evidence-only loop between the admitted host-resource observation runtime, the Privilege Broker, the Actuation Fulfillment rehearsal scaffold, World-State, and the dashboard.

The runtime consumes the exact in-memory `HostResourceRuntimeEvaluation` produced during the daemon maintenance tick. It never reruns host collectors, rebuilds telemetry snapshots, reevaluates host-resource pressure, or reevaluates host-resource policy. It requests `AuthorityClass.PROPOSAL_EVALUATION` admission only for metadata classification and rehearsal construction; that admission is not privileged-effect admission, operator approval, fulfillment, or execution.

For each valid proposal-only host-resource receipt, the coordinator records a single deterministic chain:

1. source host-resource proposal receipt;
2. privilege-broker eligibility decision;
3. privilege-broker review receipt;
4. fulfillment rehearsal plan;
5. fulfillment rehearsal receipt;
6. atomic external runtime bundle;
7. same-tick World-State facts;
8. authenticated read-only dashboard projection at `/api/world-state/host-privilege-review`.

Invalid, malformed, tampered, duplicated, or effect-claiming source receipts fail closed and are represented as invalid source items without invoking broker or fulfillment builders for that item. Denied, deferred, quarantined, missing, or malformed admission calls zero broker and fulfillment builders.

## Non-authority boundaries

The runtime is metadata-only and rehearsal-only. It does not grant operator privileged approval, privileged-effect admission, real fulfillment, backend execution, effect proof, rollback execution, host mutation, fan/PWM control, thermal or power mutation, service restart, process termination, package or driver installation, file cleanup/deletion, provider invocation, network egress, prompt assembly, repository mutation, or Git operation.

## Artifacts

Bundles are written only under an injectable external runtime-state root. The bundle includes the runtime plan, admission reference, source host evaluation reference, proposal manifest, broker decisions, broker review receipts, rehearsal plans, rehearsal receipts, validation findings, summary JSON, deterministic Markdown, and a compact latest pointer.

## Validation

Primary validation lane:

```bash
python -m scripts.run_tests -q tests/test_host_privilege_review_runtime.py tests/test_build_host_privilege_review_runtime_script.py tests/test_host_resource_runtime.py tests/test_host_resource_policy.py tests/test_privilege_broker.py tests/test_actuation_fulfillment.py tests/test_host_embodiment_trace.py tests/test_sentientosd_runtime_closure.py tests/test_world_state_board.py tests/test_dashboard_world_state.py tests/test_capability_registry.py tests/test_reviewer_proof_bundle.py tests/test_codex_validation_matrix_lane_contract.py tests/test_repository_mutation_custody_regression.py
```
