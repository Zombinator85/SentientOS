# Resident epistemic calibration review capability

## Campaign milestone

**Chosen goal:** Connect one durable forecast calibration event to a later
epistemic update through exact review and mutation admissions.

**Why this matters:** `PersistentEpistemicStateOwner` already stores calibration
events and exposes their bound outcomes to later cognition. The capability
registry still defers calibration runtime composition. Current calibration
context tests use a controlled responder and do not demonstrate an admitted
calibration review followed by an admitted update to persistent state.

**Acceptance criteria:**

1. A review request names one exact calibration event, its proposition, its
   historical forecast state, and its source evidence bindings.
2. Deterministic validation rejects missing, withdrawn, foreign, future, or
   evidence-inconsistent inputs. A caller-supplied comparison label cannot
   override the bound evidence relations.
3. A calibration-review admission constructs only a proposal. A distinct
   existing epistemic state-update admission remains required for compare-and-
   swap persistence; the update is idempotent and restart-verifiable.
4. A restart-spanning counterfactual shows that admitted calibration changes a
   later cognition or planning decision, while withheld or inconsistent
   calibration does not.

**Scope and constraints:** Reuse persistent epistemic custody, the existing
mutation controller, and prior-only cognition. Do not let calibration grant
truth, confidence, policy, goals, permissions, or action authority. Do not alter
resource-governance PR #3629. No GPU or real-model result is required for the
software milestone.

**Stop condition:** The bounded admitted path and counterfactual pass focused
tests, its authority definition is registered through the existing operator-
approval workflow, and the required hosted gate passes. Real-model benefit
remains a separate unproven question.

## Proposed authority definition (not registered)

The capability registry explicitly defers calibration runtime composition
under separate authority. This proposal therefore does not reuse the generic
epistemic state-mutation definition as permission to consume calibration
metadata.

```text
capability_id: resident_epistemic_calibration_review
subsystem_kinds: [epistemics]
principal_kinds: [deterministic_resident_epistemic_calibration_controller]
required_effects:
  - exact_epistemic_calibration_record_read
  - exact_epistemic_forecast_state_read
  - exact_epistemic_outcome_binding_read
  - deterministic_calibration_evidence_consistency_validation
  - bounded_calibration_update_candidate_construction
```

Definition digest:

```text
d36226d1f3486bfcf24951c818772af744683c4523aa96190f47aa8fd076f285
```

The exact registration task name is
`register_resident_epistemic_calibration_review_definition`. Its eventual
operator approval must bind that task name and digest. The required approval
record shape is:

```json
{
  "schema_version": "sentientos.authority_definition_operator_approval:v1",
  "approval_status": "approved",
  "approved_capability_id": "resident_epistemic_calibration_review",
  "approved_definition_digest": "d36226d1f3486bfcf24951c818772af744683c4523aa96190f47aa8fd076f285",
  "approved_task_name": "register_resident_epistemic_calibration_review_definition",
  "evidence_id": "<operator-supplied>",
  "operator_identity_label": "<operator-supplied>",
  "evidence_digest": "<recompute-after-operator-values-are-supplied>"
}
```

The candidate requires exact calibration, forecast, and evidence identities;
deterministic agreement between the comparison label and bound evidence; an
all-false-authority proposal; and a separate state-update admission with CAS,
immutable lineage, receipt, and reconstruction verification. The review
capability itself has no mutation effect. Registration alone grants no runtime
admission.

The registration workflow requires operator-supplied approval evidence bound
to this exact capability ID, definition digest, and task name. No approval
evidence is present in this proposal, and none is inferred from a general
development instruction. The exact operator approval and registration task
must be supplied before this definition can enter the canonical authority
catalog or runtime code can issue its admission.
