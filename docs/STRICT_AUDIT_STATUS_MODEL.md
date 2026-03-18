# Strict Audit Status Model

SentientOS now emits a deterministic strict-audit classification layer so operators and automation can interpret strict audit-chain posture without manually decoding mixed runtime/baseline/recovery signals.

## Canonical Buckets

`glow/contracts/strict_audit_status.json` emits one explicit bucket:

- `healthy_strict`
- `healthy_reanchored`
- `broken_preserved_nonblocking`
- `degraded_runtime_split`
- `blocking_chain_break`
- `missing_required_audit_artifacts`
- `indeterminate_audit_state`

## Inputs Used For Classification

The classifier evaluates:

- privileged baseline/runtime strict probe outcomes
- audit-chain verification + recovery state
- explicit checkpoint / continuation anchor semantics
- environment/tooling issues (e.g. missing `git` in PATH)
- required artifact presence

This model **does not rewrite or erase broken history**. It only normalizes interpretation.

## Readiness Semantics

- **Blocking**: `blocking_chain_break`, `missing_required_audit_artifacts`
- **Degraded**: `degraded_runtime_split`, `indeterminate_audit_state`
- **Acceptable under preserved-history doctrine**: `healthy_strict`, `healthy_reanchored`, `broken_preserved_nonblocking`

## Canonical Artifacts

`python scripts/verify_audits.py --strict --json` now emits and/or refreshes:

- `glow/contracts/strict_audit_status.json`
- `glow/contracts/strict_audit_breakdown.json`
- `glow/contracts/strict_audit_recovery_links.json`
- `glow/contracts/strict_audit_manifest.json`
- `glow/contracts/final_strict_audit_digest.json`

## Operator Triage

1. Read `strict_audit_status.json` for bucket + blocking/degraded flags.
2. If not healthy, inspect `strict_audit_breakdown.json` for deterministic reasons.
3. Use `strict_audit_recovery_links.json` to jump directly to recovery checkpoints, chain reports, and source logs.
4. Use `strict_audit_manifest.json` + `final_strict_audit_digest.json` for provenance-safe artifact integrity checks.
