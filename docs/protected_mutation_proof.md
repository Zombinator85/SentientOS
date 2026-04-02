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
python scripts/verify_kernel_admission_provenance.py --summary-only
python scripts/verify_kernel_admission_provenance.py --strict --summary-only
make protected-mutation-check
make contract-status
```

The verifier checks for:

- protected side effects missing admission linkage
- side effects without a matching kernel `allow`
- contradictory deny/allow evidence
- correlation collisions across different `action_kind` values
- malformed `admission_decision_ref` linkage
- missing expected side effects for feasible covered allow decisions

Verification modes:

- baseline-aware (default): legacy covered artifacts are surfaced as `legacy_missing_admission_link` but are non-blocking
- strict (`--strict`): any covered-scope issue fails

See `docs/PROTECTED_MUTATION_BASELINE_POLICY.md` for baseline handling policy.

## Where status now appears in normal repo flow

- `scripts.emit_contract_status` now includes a `protected_mutation_proof` domain in `glow/contracts/contract_status.json`.
- A compact status artifact is written to `glow/contracts/protected_mutation_proof_status.json` with:
  - covered scope id
  - baseline-aware and strict summaries
  - classification counts
  - overall status (`healthy`, `legacy_only`, `current_violation_present`)

Interpretation:

- `legacy_only`: currently covered surfaces have only pre-contract debt; baseline-aware mode is non-blocking.
- `current_violation_present`: current contract expectations are broken in covered scope; treat as active regression.
- Strict mode is for enforcement/cleanup passes and fails on legacy plus current issues.

Scope reminder: this status covers only the protected mutation surfaces listed above, not full-repo mutation completeness or unrelated audit-chain failures.

## Covered corridor relevance

- The explicit covered corridor mapping is emitted in machine-readable form via:
  - `glow/contracts/protected_corridor_report.json` (`covered_protected_mutation_corridor`)
  - `glow/contracts/protected_mutation_proof_status.json` (`covered_corridor`)
- Relevance is determined by explicit path-glob matching against touched paths (explicit paths or git diff paths), not semantic whole-repo impact inference.
- `not_applicable` means the current touched surface does not intersect currently covered protected-mutation domains; covered-scope global health is still reported separately.
- Ladder interaction:
  - baseline-aware: always reports covered-scope health (`healthy` / `legacy_only` / `current_violation_present`).
  - forward-enforcement: blocks fresh/current covered violations when the touched surface intersects the covered corridor.
  - strict mode: still enforces all covered-scope debt/violations when invoked; corridor relevance does not weaken strict semantics.

## Protected intent declaration (covered corridor only)

- Covered invocation paths now declare `protected_mutation_intent` at request time (not after-the-fact only):
  - `scripts/generate_immutable_manifest.py` (`generate_immutable_manifest`)
  - `scripts/quarantine_clear.py` (`quarantine_clear`)
  - `sentientos/genesis_forge.py` (`lineage_integrate` / `proposal_adopt`)
  - `sentientos/codex_healer.py` (repair/regenesis-linked `AuthorityClass.REPAIR` control path)
- Verifier intent statuses are machine-readable and narrow:
  - `declared_and_consistent`
  - `declared_but_mismatched`
  - `undeclared_but_protected_action`
  - `declared_but_not_applicable`
  - `not_applicable`
- Intent declaration is invocation discipline only:
  - does **not** replace kernel admission or fail-closed boundaries,
  - does **not** widen protected coverage beyond current corridor domains,
  - does **not** weaken forward-enforcement or strict mode.

## Execution consistency (covered corridor only)

Execution consistency is a narrow comparison between three machine-readable facts for covered protected actions:

1. declared protected intent (`domains` + `authority_classes`),
2. admitted kernel decision (`action_kind` + `authority_class` + disposition),
3. observed protected side effect domain (artifact/ledger row tied by `correlation_id`).

Statuses are explicit and corridor-scoped:

- `consistent`
- `declared_domain_mismatch`
- `declared_authority_mismatch`
- `side_effect_domain_mismatch`
- `admitted_but_missing_expected_side_effect`
- `undeclared_side_effect`
- `not_applicable`

Outcome rollups stay narrow (`declared_and_consistent`, `declared_but_mismatched`, `execution_drift_detected`, etc.) and integrate with corridor relevance + enforcement ladder:

- corridor `not_applicable` remains non-blocking for untouched surfaces,
- forward-enforcement blocks fresh consistency violations on relevant touched corridor surfaces,
- strict mode still blocks all covered-scope violations (legacy + current),
- execution consistency augments reporting and does **not** replace admission or fail-closed write boundaries.

## Scoped non-bypass verification (covered corridor only)

The verifier now includes a bounded non-bypass pass for the currently covered protected-mutation corridor domains only. It uses explicit model mapping (canonical boundary, expected admitted action/authority, protected artifact domain, and allowed writer surfaces) and narrow source scanning to detect **obvious** alternate mutation paths.

Machine-readable statuses:

- `no_obvious_bypass_detected`
- `alternate_writer_detected`
- `unadmitted_operator_path_detected`
- `uncovered_mutation_entrypoint_detected`
- `canonical_boundary_missing`

What counts as obvious bypass in this pass:

- direct covered-artifact writes from non-canonical writer surfaces,
- operator-facing script paths that write covered artifacts without visible admission/provenance discipline,
- missing canonical boundary mapping for a covered side-effect class.

What this does **not** prove:

- not whole-repo control-flow non-bypass proof,
- not semantic equivalence checking for all possible mutation paths,
- not coverage beyond currently covered protected-mutation domains.

Interaction rules remain strict:

- protected intent declaration remains required where integrated,
- execution consistency remains separately reported,
- forward-enforcement blocks fresh covered-scope bypass findings,
- strict mode remains at least as strict as forward-enforcement,
- kernel admission + fail-closed provenance boundaries are not replaced.

## Covered corridor trust posture (derived summary)

Protected-mutation proof now emits a machine-readable **trust posture** per covered corridor domain. This is a derived summary layer built from existing evidence classes:

- kernel-admission/provenance issue classifications,
- protected-intent statuses,
- execution-consistency statuses/outcomes,
- scoped non-bypass statuses,
- mode semantics (baseline-aware / forward-enforcement / strict).

Status vocabulary is intentionally narrow and deterministic:

- `trusted`
- `legacy_only`
- `forward_risk_present`
- `strict_failure_present`
- `not_applicable`
- `evidence_incomplete`

Two posture views are emitted and must be interpreted separately:

- `global_covered_scope`: covered-scope health posture independent of current touched-path relevance.
- `current_change_surface`: touched-path-local posture (`not_applicable` outside currently implicated covered domains).

Trust posture does **not** replace detailed verifier output. It preserves domain evidence counts and references so operators can move from summary posture back to underlying evidence for audit/debug.

## Current limits

- Verification only covers the linked protected mutation surfaces above.
- It validates current artifacts and does not repair historical drift.
- It is intentionally narrow and does not replace repo-wide audit chain verification.
- It does not assert global side-effect completeness outside covered artifact classes.
