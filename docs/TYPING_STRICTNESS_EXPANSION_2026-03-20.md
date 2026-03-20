# Strictness Expansion + Exclude Reduction (2026-03-20)

## Scope of this pass

This pass tightened the canonical typing contract without changing runtime/governor/federation architecture.

## A) Strictness expansion audit

### Promotable deferred/excluded surfaces reviewed

| Surface | Prior status | Effort/Risk | Payoff | Decision |
|---|---|---:|---:|---|
| `escrow/*`, `godot_avatar_demo/*`, `pulse/*` | Canonical exclude | Low / Low | Medium (less historical config debt) | Removed from canonical excludes (non-Python surfaces). |
| `sentientos/trust_ledger.py` | Mature, previously cleaned | Low / Low | High | Promoted into enforced strict set + protected scope. |
| `sentientos/observatory/fleet_health.py` | Mature, previously cleaned | Low / Low | High | Promoted into enforced strict set + protected scope. |
| `sentientos/diagnostics/drift_detector.py` + `drift_alerts.py` | Mature, previously cleaned | Low / Low | High | Promoted into enforced strict set + protected scope. |
| `sentientos/pulse_trust_epoch.py`, `sentientos/federation/consensus_sentinel.py`, `sentientos/runtime_governor.py` | Protected/runtime-critical | Medium / Low | High | Promoted into enforced strict set. |
| Forge corridor (`sentientos/forge*.py`, `forge_cli/*`) | Existing strict-pattern debt | High / Medium | High | Intentionally deferred; no over-promotion in this pass. |

## B) Exclude-list reduction

Canonical excludes were reduced from:

- `tests/*`, `*/tests/*`, `escrow/*`, `godot_avatar_demo/*`, `glow/*`, `pulse/*`

to:

- `tests/*`, `*/tests/*`, `glow/*`

Rationale: removed entries were historical leftovers with no Python files in canonical mypy scope.

## C) Protected/ratcheted scope expansion

- Expanded `protected_patterns` to include:
  - `sentientos/diagnostics/*.py`
  - `sentientos/observatory/*.py`
  - `sentientos/trust_ledger.py`
  - `sentientos/pulse_trust_epoch.py`
- Added `strict_enforced_patterns` for deterministic strict checks on mature, healthy modules.

## D) Cleanup required to enable promotion

- `scripts/mypy_ratchet.py`: added explicit list/int normalization helpers to satisfy strict typing and keep policy parsing deterministic.
- `scripts/verify_audits.py`: added typed strict-output payload and optional-flow narrowing for strict compliance.

## E) Canonical artifact posture

Regenerated via canonical command (`python scripts/mypy_ratchet.py`) with green status.

- `glow/contracts/canonical_typing_baseline.json`
- `glow/contracts/typing_cluster_summary.json`
- `glow/contracts/typing_ratchet_status.json`
- `glow/contracts/final_typing_baseline_digest.json`

`typing_ratchet_status.json` now carries additional strictness observability fields (`policy_strict_status`, `policy_strict_target_count`, `excluded_glob_count`).

## F) What remains intentionally deferred

- Existing forge strict-pattern debt remains explicit and deferred; this pass avoided over-promoting unstable surfaces.
- Broad repo-wide legacy untyped boundaries remain governed by ratcheted-new-debt rules.

## Next likely strictness-expansion targets

1. `scripts/emit_contract_status.py` strict cleanup.
2. `scripts/tooling_status.py` strict cleanup (high payoff, higher effort).
3. Targeted forge submodules with lowest strict error density (`forge_cli/types.py`, `forge_progress_contract.py`) before wider forge strict enforcement.
