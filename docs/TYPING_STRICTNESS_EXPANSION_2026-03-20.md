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

---

# Strictness Expansion + Typed Mainland Promotion (2026-03-24)

## Scope of this pass

This pass performed one broad constitution update: promote newly healthy mainland modules into enforced strict posture, tighten ratchet truthfulness, and remove stale baseline fiction from canonical artifacts.

## A) Strictness expansion audit

### Candidate audit matrix (pre-implementation)

| Cluster | Prior status | Effort/Risk | Payoff | Promotion decision |
|---|---|---:|---:|---|
| `control_plane/*` | promotable candidate | Low / Low | High | Promoted to protected + strict-enforced. |
| `reporters/*` | promotable candidate | Low / Low | Medium | Promoted to protected + strict-enforced. |
| `council/*` + `council/adapters/*` | near-promotable (small structural typing gaps) | Medium / Low | High | Cleaned and promoted to protected + strict-enforced. |
| `api/*` | near-promotable (decorator typing + return contracts) | Medium / Low | High | Cleaned and promoted to protected + strict-enforced. |
| `scripts/audit_immutability_verifier.py` | protected-only | Medium / Low | High | Strict-cleaned and promoted to strict-enforced. |
| `scripts/emit_baseline_verification_status.py` | protected candidate | Low / Low | Medium | Strict-cleaned and promoted to strict-enforced. |
| `sentientos/audit_strict_status.py` + `sentientos/ci_baseline.py` | strict-near-ready | Low / Low | Medium | Strict-cleaned and promoted to strict-enforced. |
| `sentientos/forge*` strict aspirational set | strict pattern with active debt | High / Medium | High | Kept deferred from enforcement; remains visible as strict candidates. |

## B) Canonical baseline honesty fix (ratchet parser hardening)

`scripts/mypy_ratchet.py` now recognizes non-position mypy errors (for example duplicate-module failures that previously escaped parsing). This removed a major blind spot where canonical artifacts could report zero debt despite true mypy failures.

## C) Exclude/deferred territory adjustments

Canonical excludes were adjusted to avoid known duplicate-module collisions while preserving deterministic whole-repo scans:

- Added `privilege_lint.py` (duplicate module with package `privilege_lint/`)
- Added `sentientos/codex.py` (duplicate module with package `sentientos/codex/`)

These exclusions are structural and auditable; they prevent parser-level hard stops and let canonical debt accounting proceed.

## D) Protected/strict mainland expansion

Promoted into both `protected_patterns` and `strict_enforced_patterns`:

- `control_plane/*.py`
- `reporters/*.py`
- `council/*.py`
- `council/adapters/*.py`
- `api/*.py`
- `scripts/audit_immutability_verifier.py`
- `scripts/emit_baseline_verification_status.py`
- `sentientos/audit_strict_status.py`
- `sentientos/ci_baseline.py`

Result: enforced strict targets expanded to include key operator/API/governance mainland surfaces.

## E) Cleanup completed to make promotions real

- `council/runner.py`: added adapter protocol for typed multi-adapter orchestration.
- `council/schema.py`: tightened mapping return type.
- `api/federation_api.py`, `api/federation_stream_api.py`: introduced typed route decorators and hardened response payload typing.
- `scripts/audit_immutability_verifier.py`: normalized manifest/event typing, defensive manifest-shape checks, strict-safe logging contracts.
- `scripts/emit_baseline_verification_status.py`: strict-safe JSON/cast handling.
- `sentientos/audit_strict_status.py`, `sentientos/ci_baseline.py`: strict-safe return typing.
- `scripts/verify_audits.py`: narrowed strict bucket handling to preserve literal typing under strict mode.

## F) Canonical artifact state after promotion

Regenerated and now truthful under hardened parsing:

- `glow/contracts/mypy_baseline.json` refreshed to real debt baseline (`error_count=2369`).
- `glow/contracts/canonical_typing_baseline.json`
- `glow/contracts/typing_cluster_summary.json`
- `glow/contracts/typing_ratchet_status.json`
- `glow/contracts/final_typing_baseline_digest.json`

`typing_ratchet_status.json` remains green (`status=ok`) with:

- no new debt over refreshed baseline,
- no protected-surface regressions,
- strict enforcement passing for expanded strict-enforced territory.

## G) Intentionally deferred territory

- `sentientos/forge*` remains strict-candidate (visible via `policy_strict_candidate_count`) but not strict-enforced until debt is reduced.
- Broad legacy debt outside promoted mainland remains ratcheted by baseline and is not hidden.

## Next likely strictness-expansion targets (post-2026-03-24)

1. `sentientos/forge_*` lowest-error modules (`forge_failures.py`, `forge_outcomes.py`, `forge_transaction.py`) for next strict-enforcement tranche.
2. `scripts/tooling_status.py` and adjacent audit emitters as next operator-surface strict promotion.
3. `api/actuator.py` contract hardening to extend strict-enforced API corridor beyond federation endpoints.
