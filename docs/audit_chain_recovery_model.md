# Audit-chain recovery and trust re-anchoring model

## Goals
- Preserve append-only evidence and immutable provenance semantics.
- Never silently rewrite broken history segments.
- Make trust boundaries explicit when continuity is broken.
- Support deterministic, auditable re-anchoring into a new trusted continuation.

## Model

### 1) Chain states
`sentientos.audit_chain_gate.verify_audit_chain()` now reports explicit states:
- `intact_trusted`: no break detected.
- `broken_preserved`: break detected, history preserved, no trusted continuation yet.
- `reanchored_continuation`: break preserved and an explicit recovery checkpoint exists whose continuation anchor matches the first continuation record.

### 2) Trust boundary artifacts
A recovery checkpoint ledger is append-only at:
- `glow/forge/audit_reports/audit_recovery_checkpoints.jsonl`

Each checkpoint records:
- break fingerprint (path + line + expected/found prev hash)
- trusted head hash before break
- continuation anchor prev hash
- continuation log path
- operator reason and timestamp

### 3) Deterministic identification
- `break_fingerprint` is deterministic hash of first-break coordinates.
- `checkpoint_id` is deterministic hash over checkpoint payload fields (excluding `checkpoint_id`).

### 4) Recovery flow
1. Detect break via `verify_audit_chain` / `verify_audits --strict`.
2. Create explicit checkpoint with:
   - `python scripts/audit_chain_reanchor.py --reason "<reason>"`
3. System remains evidence-preserving; no legacy lines are rewritten.
4. Runtime continuation can be validated against checkpoint anchor via `recovery_state.continuation_descends_from_anchor`.

### 5) Observability
Audit chain reports now include:
- `trusted_history_head_hash`
- `recovery_state` with checkpoint linkage, history state, degraded mode flag, and trust boundary explicitness.

## Limitations
- Re-anchoring does not repair corrupted legacy segments; it only establishes an explicit trust restart boundary.
- Continuation verification currently checks the first continuation entry anchor only.
- Checkpoint records are repository-local evidence; cryptographic signatures are not yet enforced.
