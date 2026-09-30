# Governed local-model budget allocation contract

This document is the narrative companion to `architecture/governed_local_model_budget_allocation_contract.json` (`sentientos.governed_local_model_budget_allocation_contract:v1`). The JSON is the normative closed contract. It records repository revision `8a1ce976cc488c53a6c42d2a1592611038f945a8`. This slice defines architecture only: no allocator, allocation, ledger, debit, meter, resource gate, runtime receipt, authority registration, grant, admission, or effect is implemented.

## Five independent answers

| Question | Exact answer |
|---|---|
| Whose causal work? | One canonical, independently issuer-authenticated, currently verified `CausalResourcePrincipal`. |
| What resource may be spent? | A `ResourceAllocation` specialized to `governed_local_model_invocation_call_entitlement.v1`. |
| May inference occur? | Only under the separate existing `LOCAL_MODEL_INFERENCE` effect admission. |
| Is the model operationally current? | Only under the separate serving-lifetime currentness check and model authority/configuration ceilings. |
| What was attempted/consumed? | A future, separate, append-only `GovernedLocalModelResourceConsumptionReceipt`. |

Currentness is observation, not allocation. A caller budget is a request ceiling, not entitlement. Model authority/configuration, serving currentness, effect admission, resource entitlement, and receipts do not manufacture one another.

## Current source semantics and bound classification

`LocalModelInvocationBudget` currently has exactly five fields. The first adapter conserves only calls:

| Field | v1 law | Exact current behavior | Conserved? |
|---|---|---|---|
| `max_input_chars` | per-attempt feasibility ceiling | `len(prompt)` counts Python Unicode code points, although the request's separate `prompt_size` records UTF-8 bytes | No aggregate conservation; actual input length is measurable. |
| `max_output_chars` | per-attempt returned-output ceiling | only after generation, UTF-8 bytes are compared and byte-truncated with decoding errors ignored; the name does not match the enforced byte unit | No. Generated and returned byte sizes can be measured, but truncation does not prevent generation compute. |
| `max_new_tokens` | per-attempt generation ceiling | passed to the backend after taking the minimum with the authority record's applicable `max_new_tokens` ceiling | No. It is configured, while exact actual token use is unavailable. |
| `timeout_seconds` | temporal ceiling | waits on the generation future, with a minimum wait of 0.001 seconds; cancellation does not prove backend work stopped | No. Latency is measurable, but time is not refundable currency. |
| `max_calls_per_correlation` | discrete consumable entitlement in the specialized allocation | the present `invocation_counts` check/increment is correlation-keyed, process-local, and resets on restart | Yes in the future adapter. The legacy map remains only a component safeguard and is not a ledger. |

The legacy field name remains for compatibility, but the allocation's count is durable across correlations and restarts. The authoritative allocation—not caller serialization—owns it.

For every positive finite dimension, the effective value is the numeric minimum of the allocation bound, a caller-requested budget, and any applicable model/serving ceiling. Integer fields reject booleans. Absence of caller narrowing uses the allocation value; absence of an applicable model ceiling adds no limit. A broader caller/model value is rejected or reduced and can never expand allocation. `LocalModelAuthorityRecord` is not an allocation and neither record manufactures the other.

## Allocation schema, identity, and validity

`GovernedLocalModelResourceAllocation` contains exactly:

`allocation_id`, `principal_binding_digest`, `principal_id`, `principal_epoch`, `resource_kind`, `resource_specific_bounds`, `validity`, `allocator_id`, `epoch`, `policy_digest`, and `allocation_digest`.

The two explicit principal fields make substitution and review visible, while `principal_binding_digest` remains authoritative. Correlation, caller linkage, and `work_item_id` are not identity. `allocator_id` is exactly `sentientos.governed_local_model_resource_allocator.v1`. `epoch` is the allocator-controlled, positive, monotonic allocation-policy generation. It is not principal epoch, validity, or serving activation generation.

Closed canonical JSON uses UTF-8, sorted keys, comma/colon separators, ASCII escaping, finite JSON numbers, no duplicate/unknown/missing keys, no mutable aliases, and no wildcards. `policy_digest` is SHA-256 over the exact immutable canonical policy snapshot. `allocation_digest` is SHA-256 over every allocation field except `allocation_id` and `allocation_digest`; `allocation_id` is `lmalloc-` plus its first 24 hex characters. Caller-supplied `allocated=true` is meaningless and forbidden.

Validity is the intersection of allocation validity, principal natural validity, bounded currentness-snapshot validity, allocator-policy validity, and any resource lease (v1 adopts no additional lease). Effective start is their maximum start; effective end is their minimum end, with `start <= now < end`. Issuance and final debit reverify the exact authenticated principal and bounded snapshot. A snapshot never implies live currentness past `valid_until`; known revocation or supersession blocks. The allocation cannot outlive any evidence on which it depends.

## Lifecycle, charging, retries, and crashes

The minimal states are issued/unbegun, attempt begun, measured completed/timeout/backend failure, remaining or exhausted, and expired/revoked. The atomic durable final-gate debit is sufficient; v1 adds no separate reservation subsystem.

A unique attempt ID is `lmattempt-` plus 32 hex characters from SHA-256 of canonical `{allocation_digest,durable_attempt_nonce}` and must be durably uniqueness-checked. Pre-attempt structural, feasibility, principal, allocation, or admission rejection consumes zero. The final gate provisionally debits immediately before the existing serving pre-effect guard and generation. If trusted evidence proves that guard rejected before backend entry, reconciliation records `attempted_not_begun` and restores the debit. Once backend generation entry begins, exactly one call is consumed. Completion, timeout, cancellation, or backend failure after entry never refunds it. Every retry needs a fresh attempt ID and another remaining unit; changing a correlation ID or restarting cannot replenish prior consumption.

Therefore v1 requires durable atomic attempt uniqueness, remaining-count/debit state, an append-only receipt chain, and crash recovery/reconciliation **before activation**. Today's process-local `invocation_counts` cannot satisfy this claim.

Exhaustion may only block, defer, narrow, safely degrade, or terminate. It cannot widen authority, silently substitute a model without separate authorization, mint another allocation, reset usage, or bypass serving checks.

## Required eventual order

1. Request structural validation.
2. Model and serving feasibility validation.
3. Authenticated and current causal-principal verification.
4. Allocation existence/structure verification and early narrowing only.
5. Existing independent `LOCAL_MODEL_INFERENCE` effect admission.
6. Final current allocation check and atomic durable call debit.
7. Existing serving-lifetime pre-effect currentness guard.
8. Model generation attempt.
9. Resource measurement.
10. Resource receipt/reconciliation.
11. Existing effect receipt completion and cross-link.

Early allocation inspection may narrow or block, but never authorizes an effect. The final resource gate is after otherwise-valid effect admission and immediately before the serving guard/model attempt.

## Consumption receipt

The future specialized record contains `receipt_id`, `allocation_digest`, `principal_binding_digest`, `attempt_id`, `resource_specific_measurement`, `state`, `observed_at`, `previous_receipt_digest`, `effect_receipt_digest`, and `receipt_digest`. States are `attempted_not_begun`, `attempt_begun`, `measured_completed`, `measured_timeout`, `measured_backend_failure`, and `reconciled`. Corrections append; they never edit.

Truthful present measurements are generation-attempted status, generated/returned UTF-8 byte sizes when available, truncation, latency, configured ceilings, outcome, and admission reference. Exact token use is `null`/unavailable until trusted backend usage exists. CPU, GPU, RAM, energy, and proof that timed-out compute stopped are not claimed.

`effect_receipt_digest` is null until an effect receipt exists; reconciliation appends a hash-linked resource receipt referencing the exact `LocalModelInvocationReceipt.receipt_digest`. A resource receipt is not an effect receipt, consumption does not imply output success, and an effect does not imply reconciliation completed.

## Candidate future task authority (not registered)

The exact candidate definition is:

- capability: `governed_local_model_resource_allocation_adapter`
- subsystem: `causal_resource_principal_architecture`
- principal kind: `governed_local_model_resource_allocator`
- effects: `check_and_debit_governed_local_model_call_entitlement`, `issue_governed_local_model_resource_allocation`, `read_current_causal_resource_principal_evidence`, `read_governed_local_model_resource_policy`, `write_governed_local_model_resource_consumption_receipt`
- required goal phrases: `governed local-model resource allocation`; `durable call conservation`; `resource consumption receipt`
- forbidden goal phrases: `generic resource allocator`; `host scheduling`; `model effect admission`; `provider invocation`; `network egress`; `grant local model inference`
- approvals: `independent_operator_approval_evidence`; `exact_definition_digest_binding`
- purpose: implement only this resource allocator, durable call gate, and reconciliation; grant no model effect authority.

Repository-native `authority_definition_digest(...)` canonical serialization is:

```json
{"approval_requirements":["independent_operator_approval_evidence","exact_definition_digest_binding"],"capability_id":"governed_local_model_resource_allocation_adapter","forbidden_goal_phrases":["generic resource allocator","host scheduling","model effect admission","provider invocation","network egress","grant local model inference"],"principal_kinds":["governed_local_model_resource_allocator"],"purpose":"Implement only the governed local-model invocation resource allocator, durable call-entitlement gate, and resource-consumption reconciliation defined by the frozen v1 contract; this definition grants no model effect authority.","required_effects":["check_and_debit_governed_local_model_call_entitlement","issue_governed_local_model_resource_allocation","read_current_causal_resource_principal_evidence","read_governed_local_model_resource_policy","write_governed_local_model_resource_consumption_receipt"],"required_goal_phrases":["governed local-model resource allocation","durable call conservation","resource consumption receipt"],"subsystem_kinds":["causal_resource_principal_architecture"]}
```

Its digest is `f6ba71581fa862097cb279fe0ed47d2d008a6af9e9eef21169b01e6cd8605ebc`.

The approval template deliberately contains placeholders:

```json
{"schema_version":"sentientos.authority_definition_operator_approval:v1","evidence_id":"<operator-supplied-evidence-id>","operator_identity_label":"<operator-supplied-identity-label>","approval_status":"<operator-supplied-approved-status>","approved_capability_id":"governed_local_model_resource_allocation_adapter","approved_definition_digest":"f6ba71581fa862097cb279fe0ed47d2d008a6af9e9eef21169b01e6cd8605ebc","approved_task_name":"register-governed-local-model-resource-allocation-adapter-authority-definition","evidence_digest":"<computed-after-operator-supplied-fields>"}
```

Placeholders are not approval. The exact next slice is the definition-only `register-governed-local-model-resource-allocation-adapter-authority-definition` task after independent approval. Its repository-native artifact has `task_classification=AUTHORITY_DEFINITION_REGISTRATION` (serialized as `authority_definition_registration`), that exact `task_name`, `definitions=(candidate,)`, and `operator_approval=<exact independently supplied evidence>`, while `requested_capability_id=""`, `authority_principal=""`, `requested_effects=()`, and `runtime_mutations=()`. The exact bounded `changed_paths` tuple is `("sentientos/codex_task_authority_admission.py", "tests/test_authority_definition_registration.py", "docs/architecture/governed_local_model_budget_allocation_contract.md")`.

The JSON payload uses lists because JSON has no tuple or frozenset type. Conversion is exact: its sole `definitions` object becomes the frozen candidate `TaskAuthorityDefinition`; `subsystem_kinds`, `principal_kinds`, and `required_effects` become `frozenset` values; phrase and approval requirement lists become tuples; and `requested_effects`, `runtime_mutations`, and `changed_paths` become tuples without changing their values. The singular `definition` and `operator_approval_evidence` keys are not registrar inputs and are forbidden from this handoff. Registration may not exercise or self-authorize the definition. Definition is not grant; grant is not admission; registration is not implementation; implementation is not activation.

## Explicit deferral

Deferred are the runtime allocation type, allocator, durable ledger, gate/debit, metering, receipt implementation, all invocation/serving/control-plane changes, authority registration, operator approval, allocation issuance, exact tokens, physical-resource accounting, and activation. The selected next slice is registration only—not allocator implementation.
