# Audit Recovery and Strict Readiness

This runbook explains how strict audit readiness is derived from preserved broken history + explicit re-anchor semantics.

## Core Principle

SentientOS preserves broken history for audit truth; it never silently rewrites past breaks. Strict readiness therefore depends on **classification of current trust posture**, not deletion of historical evidence.

## Recovery States and Strict Outcomes

### 1) Historical chain intact
- Chain: `ok`
- Strict bucket: `healthy_strict`
- Readiness: acceptable

### 2) Re-anchor checkpoint + trusted continuation
- Chain: `reanchored`
- Continuation descends from checkpoint anchor
- Strict bucket: `healthy_reanchored`
- Readiness: acceptable

### 3) Broken history preserved with explicit checkpoint
- Historical break remains visible
- Checkpoint exists, runtime can still continue safely
- Strict bucket: `broken_preserved_nonblocking`
- Readiness: acceptable (non-blocking preserved-history doctrine)

### 4) Runtime split / continuation ambiguity
- Checkpoint or runtime exists, but continuation trust is not clean
- Strict bucket: `degraded_runtime_split`
- Readiness: degraded (triage required)

### 5) Unresolved or hard failures
- No valid recovery anchor for break, or required strict artifacts missing
- Strict bucket: `blocking_chain_break` or `missing_required_audit_artifacts`
- Readiness: blocking

### 6) Environment/tooling execution failures
- Tool invocation/path issues distinguished from chain-state regression
- Strict bucket: `indeterminate_audit_state`
- Readiness: degraded (fix environment first, then re-run strict verification)

## Observatory + Contract Consumption

- Fleet observatory reads `glow/contracts/strict_audit_status.json` as `strict_audit_health`.
- Artifact provenance index publishes strict audit status as a first-class surface.
- Contract status tracks strict audit status artifact presence.

## Primary Commands

- `python scripts/verify_audits.py --strict --json`
- `python -m sentientos.audit verify -- --strict --json`
- `python -m sentientos.ops observatory fleet --json`
- `python -m sentientos.ops observatory artifacts --json`

## What This Pass Does Not Change

- Trust epoch / quorum / truth-oracle / contradiction-policy behavior
- Existing runtime/federation/governor architecture
- Append-only provenance and immutable manifest doctrine
- Deterministic cycle-boundary and semantic invariant enforcement
