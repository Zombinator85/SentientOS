# Runtime Posture Composition Model

This note defines the explicit, deterministic posture model used by `RuntimeGovernor`.

## Goals

- Keep admission decisions rule-based, deterministic, bounded, and auditable.
- Compose pressure, storm, audit trust, fairness/starvation, and context dimensions explicitly.
- Emit per-action explanation data in `/glow/governor/` artifacts.

## Core concepts

- **effective_posture**: `nominal`, `constrained`, or `restricted`.
- **posture_reason_chain**: ordered rule evaluations (dimension, reason, restriction class, precedence, block flag).
- **dominant restriction cause**: highest-precedence reason that determines the externally visible reason.
- **active posture dimensions**: pressure band/composite, storm flag, fairness streak, scope, class/family/priority, deferrable/local-safety flags.
- **posture escalation ladder**: set of active restriction classes (`audit_trust`, `local_safety`, `storm`, `pressure`, `contention`, `fairness`, `budget`, `policy`).

## Deterministic precedence

Precedence is static and integer-ranked:

1. Audit trust gates (`100`)
2. Local safety guard under federated pressure (`90`)
3. Storm-federation restrictions (`80`)
4. Budget/pressure base gates (`70`)
5. Recovery arbitration overrides (`65`)
6. Reserved-slot contention (`60`)
7. Fairness starvation restriction (`55`)
8. Low-priority/contention arbitration (`50/45`)
9. Nominal markers (`40` and below)

When multiple dimensions are active, the dominant reason is chosen by:

- descending precedence,
- then lexical reason ordering,
- then lexical dimension ordering.

This makes tie behavior deterministic.

## Artifact surface

Per decision (`decisions.jsonl`) and observability (`observability.jsonl`) now include:

- `runtime_posture`
- `runtime_posture.effective_posture`
- `runtime_posture.active_dimensions`
- `runtime_posture.reason_chain`
- `dominant_restriction_cause`

Rollup includes `runtime_posture_summary` as a bounded aggregate.

## Known blind spots

- Fairness currently uses denied-streak and contention pressure; it does not yet model weighted per-subject debt repayment.
- Multi-action transactional posture (cross-action atomic bundles) is not yet represented.
- Federation trust posture is currently represented through admission context and audit trust, not a separate cryptographic quality gradient.
