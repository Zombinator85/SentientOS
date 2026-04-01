# Protected Mutation Proof Surface

This repository currently requires control-plane kernel admission for these high-impact mutation paths:

- `lineage_integrate` and `proposal_adopt` in GenesisForge (`AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION` and `AuthorityClass.PROPOSAL_ADOPTION`).
- `generate_immutable_manifest` for identity/manifest writes (`AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION`).
- `quarantine_clear` operator action (`AuthorityClass.PRIVILEGED_OPERATOR_CONTROL`).
- Runtime repair actions mediated by `CodexHealer` (`AuthorityClass.REPAIR`), including regenesis escalation decisions.

## Correlation and linkage

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

Protected side-effect artifacts now carry the same linkage where practical:

- Genesis lineage entries (`lineage/lineage.jsonl`) and adoption artifacts (live daemon payload + codex index entry).
- Immutable manifest payload (`vow/immutable_manifest.json` under `admission`).
- Quarantine clear forge events (`pulse/forge_events.jsonl` for `integrity_recovered` and deny events).
- Codex healer ledger entries (`details.kernel_admission`).

## How to verify

Run:

```bash
python scripts/verify_kernel_admission_provenance.py
```

The verifier checks for:

- protected side effects missing admission linkage
- side effects without a matching kernel `allow`
- contradictory deny/allow evidence
- correlation collisions across different `action_kind` values

## Current limits

- Verification only covers the linked protected mutation surfaces above.
- It validates current artifacts and does not repair historical drift.
- It is intentionally narrow and does not replace repo-wide audit chain verification.
