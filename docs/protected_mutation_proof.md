# Protected Mutation Proof Surface

This repository currently requires control-plane kernel admission for these high-impact mutation paths:

- `lineage_integrate` and `proposal_adopt` in GenesisForge (`AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION` and `AuthorityClass.PROPOSAL_ADOPTION`).
- `generate_immutable_manifest` for identity/manifest writes (`AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION`).
- `quarantine_clear` operator action (`AuthorityClass.PRIVILEGED_OPERATOR_CONTROL`).
- Runtime repair actions mediated by `CodexHealer` (`AuthorityClass.REPAIR`), including regenesis escalation decisions.

## Covered protected-mutation contract (current scope)

- Kernel decisions are appended to `glow/control_plane/kernel_decisions.jsonl`.
- Every decision row includes:
  - `correlation_id`
  - `action_kind`
  - `authority_class`
  - `lifecycle_phase`
  - `final_disposition`
  - `delegate_checks_consulted`
  - `execution_owner`
  - `admission_decision_ref` (`kernel_decision:<correlation_id>`)

Required provenance fields for allow-path protected mutation writes in this scope:

- `correlation_id`
- `admission_decision_ref`
- `action_kind`
- `authority_class`
- `lifecycle_phase`
- `final_disposition`
- `execution_owner`

For deny/defer/quarantine admission records, required non-execution fields are:

- `correlation_id`
- `admission_decision_ref`
- `action_kind`
- `authority_class`
- `lifecycle_phase`
- `final_disposition`

Protected side-effect artifacts in covered scope:

- Genesis lineage entries (`lineage/lineage.jsonl`) and adoption artifacts (live daemon payload + codex index entry).
- Immutable manifest payload (`vow/immutable_manifest.json` under `admission`).
- Quarantine clear forge events (`pulse/forge_events.jsonl` for `integrity_recovered` and `kernel_admission_denied`).
- Codex healer ledger entries (`details.kernel_admission`).

Write boundaries fail closed in this scope: covered protected mutation writes now validate the required provenance payload before writing artifacts.

## How to verify

Run targeted verification:

```bash
python scripts/verify_kernel_admission_provenance.py
make protected-mutation-check
```

The verifier checks for:

- protected side effects missing admission linkage
- side effects without a matching kernel `allow`
- contradictory deny/allow evidence
- correlation collisions across different `action_kind` values
- malformed `admission_decision_ref` linkage
- missing expected side effects for feasible covered allow decisions

## Current limits

- Verification only covers the linked protected mutation surfaces above.
- It validates current artifacts and does not repair historical drift.
- It is intentionally narrow and does not replace repo-wide audit chain verification.
- It does not assert global side-effect completeness outside covered artifact classes.
