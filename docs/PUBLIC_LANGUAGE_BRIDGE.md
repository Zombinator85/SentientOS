# Public Terminology Standard (Normalized ↔ Legacy)

This document is the canonical terminology contract for public-facing
SentientOS material.

## Policy

- Public docs, onboarding, and CLI help text must lead with normalized
  engineering language.
- Legacy symbolic wording is compatibility-only.
- Legacy terms are allowed only for historical references, stable API/field
  compatibility, or fixed filesystem namespaces.

Deterministic mappings for tooling live in `sentientos/public_language_map.py`.

## Canonical mappings

| Legacy term | Normalized public term | Migration status | Compatibility rule |
| --- | --- | --- | --- |
| cathedral | governance control plane | Deprecated public term | Only use for historical references or legacy command names. |
| council | governance authority | Deprecated public term | Keep only where external artifacts/log fields already use it. |
| blessing | privileged approval | Deprecated public term | Keep as alias for compatibility on existing interfaces. |
| ritual | operator procedure | Deprecated public term | Keep only for archival docs and legacy module names. |
| consciousness layer | deterministic state-processing layer | Deprecated public term | Use legacy wording only in compatibility notes. |
| consciousness cycle | deterministic state-processing cycle | Deprecated public term | Keep only where command/API compatibility requires it. |
| presence | activity telemetry | Replace on public surfaces | Legacy wording allowed in historical event labels. |
| observatory | observability | Replace on public surfaces | Keep as alias for existing command groups. |
| forge | governed change pipeline | Replace on public surfaces | Keep namespace alias until major-version migration. |
| self-model | runtime identity contract | Replace on public surfaces | Legacy schema keys may remain where required. |
| vow | integrity contract artifact set | Retained internal codename | `/vow` path retained for compatibility. |
| glow | state ledger artifact set | Retained internal codename | `/glow` path retained for compatibility. |
| wild-dialogue | exploratory dialogue mode | Replace on public surfaces | Legacy name stays only where rename cost is high. |

## Writing rule for public surfaces

1. Use normalized term by default.
2. Mention legacy term only when compatibility context is necessary.
3. If a legacy term is shown, mark it explicitly as **legacy** or
   **internal codename**.

Example:

- `governance authority (legacy term: council)`
- `deterministic state-processing cycle (legacy CLI label: consciousness cycle)`
