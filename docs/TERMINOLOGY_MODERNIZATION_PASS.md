# Terminology Modernization Pass (2026-03-31)

This document records the repository-wide terminology modernization strategy and
outcomes for this PR.

## Audit summary

High-friction terms identified across public docs and CLI/help surfaces:

- `cathedral`
- `council`
- `blessing`
- `ritual`
- `consciousness layer` / `consciousness cycle`
- `presence`
- `observatory`
- `forge`
- `wild-dialogue`

## Classification decisions

### Rename broadly on public surfaces

- `cathedral` → `governance control plane`
- `council` → `governance authority`
- `blessing` → `privileged approval`
- `ritual` → `operator procedure`
- `consciousness layer` → `deterministic state-processing layer`
- `consciousness cycle` → `deterministic state-processing cycle`
- `presence` → `activity telemetry`
- `observatory` → `observability`
- `forge` → `governed change pipeline`
- `wild-dialogue` → `exploratory dialogue mode`

### Keep temporarily as compatibility alias

- Existing command group names and legacy script names (`forge`, `observatory`,
  `bootstrap_cathedral.py`, `cathedral-gui`) are retained but marked legacy in
  user-facing text.
- Existing arguments like `--blessing` remain supported where external scripts
  may depend on them.

### Keep as internal codename due path/schema compatibility

- `/vow` and `/glow` namespace paths remain unchanged.

### Remove outright from public-facing guidance

- Mystical/ceremonial framing in onboarding and glossary copy (for example:
  "welcome to the cathedral", "bless your pull request", and similar language)
  has been removed from front-door docs.

## Enforcement scope expansion

Terminology enforcement now covers:

- top-level public docs (`README.md`, `CONTRIBUTING.md`, `INSTALL.md`)
- key docs under `docs/` used by contributors/reviewers
- selected CLI help text sources (`cli/sentientos_cli.py`, `doctrine_cli.py`,
  `federation_cli.py`, `treasury_cli.py`, `ritual_digest_cli.py`, `wdm_cli.py`)

Internal archives and deeply historical cultural files are intentionally out of
scope for this enforcement pass.

## Semantics and runtime invariants

This pass changes wording, guidance, and compatibility metadata only. No
runtime, governance, audit, federation, or protected-corridor logic was
modified.
