# Proof-of-Validity Framework (Phase I)

The Proof-of-Validity framework extends the SentientOS governance pipeline with
machine-checkable guarantees that every amendment honours the covenant
invariants. Each proposal now produces a structured `proof_report` that can be
reviewed, audited, and relayed to downstream services such as HungryEyes and
CodexHealer.

## Invariant Catalogue

| Invariant | Rule | Description | Severity | Proof Hint |
| --- | --- | --- | --- | --- |
| structural_integrity | `required_fields ⊆ spec_fields` | All covenant-required fields must be present in the proposed specification. | critical | Ensure the amendment includes objective, directives, and testing_requirements. |
| audit_continuity | `ledger_diff.removed == []` | Ledger continuity cannot be broken by removing historical entries. | high | Ledger diffs must only append new entries; never remove existing ones. |
| forbidden_status | `spec.status not in FORBIDDEN_STATUSES` | Proposals may not transition the amendment into forbidden lifecycle states. | high | Avoid statuses such as reboot, retired, nullified, or decommissioned. |
| recursion_guard | `not spec.recursion_break` | Recursion guard must remain intact to prevent runaway invocation loops. | high | Do not set recursion_break or recursion to break/halt within the amendment. |

The canonical invariant definition lives in [`vow/invariants.yaml`](../vow/invariants.yaml).

## Proof Report Schema

Each evaluation returns a JSON document with the following structure:

```json
{
  "valid": true,
  "violations": [
    {
      "invariant": "structural_integrity",
      "rule": "required_fields ⊆ spec_fields",
      "detail": "Missing required fields: objective",
      "severity": "critical",
      "proof_hint": "Ensure the amendment includes objective, directives, and testing_requirements."
    }
  ],
  "trace": [
    {
      "invariant": "structural_integrity",
      "rule": "required_fields ⊆ spec_fields",
      "passed": false,
      "context": {
        "required_fields": ["objective", "directives", "testing_requirements"],
        "spec_fields": ["directives", "testing_requirements"],
        "missing": ["objective"]
      }
    }
  ]
}
```

* `valid` indicates whether every invariant passed.
* `violations` lists the invariants that failed along with human-readable
  details.
* `trace` provides contextual data for each invariant evaluation. This trace is
  suitable for automated auditors and narrative systems alike.

## Integration Points

* **IntegrityDaemon** records the `proof_report` for every amendment inside
  `/daemon/integrity/ledger.jsonl`, quarantining proposals that violate the
  invariants when `proof_verification.fail_on_invalid` is enabled in
  [`vow/config.yaml`](../vow/config.yaml).
* **HungryEyes dual-control** augments the `proof_report` with additional risk
  telemetry before automated commits are authorised.
* **CodexHealer** narrates the verdict via `proof_summary`, enabling operators to
  understand how many invariants passed or failed during recovery events.

### HungryEyes training pipeline

Historical ledger entries and quarantine payloads can now be transformed into
training data via `sentientos.daemons.hungry_eyes.HungryEyesDatasetBuilder`.
The builder normalises each event into covenant-aligned features (violation
counts, invariant flags, probe outcomes) which feed the
`HungryEyesSentinel`'s interpretable logistic model.  After fitting, the
sentinel exposes detailed risk contributions that are attached to each
`proof_report` as part of the IntegrityDaemon dual-control handshake, providing
auditable evidence for autonomous approvals.

## Test Coverage

Automated coverage for the framework lives in
[`tests/test_proof_validity.py`](../tests/test_proof_validity.py). The suite
verifies:

* happy-path approval when all invariants pass,
* invariant-specific violations (structural integrity, audit continuity,
  forbidden status, recursion guard), and
* ledger integration, including quarantine behaviour for invalid proofs.
