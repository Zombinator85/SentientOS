# Invariant Enforcement

This repository guards interpretation, gradient, and boundary invariants with static tooling only. No runtime behavior is changed by these safeguards.

## What the invariant lint enforces
- Decision-path expressions must not reference reward, utility, score, optimization, survival, or persistence language.
- Operator-visible strings must not include bonding, obligation, or forward-seeking phrasing.
- Persistent counters or accumulators must be explicitly allowlisted and documented before they are written to disk or durable state.
- Scope: Python sources in `sentient_api.py`, `policy_engine.py`, and modules under `scripts/`, `codex/`, and `api/`.

## What the invariant lint does **not** enforce
- Runtime behavior, service orchestration, or any network/IO side effects.
- Dynamic evaluation of templates, database contents, or runtime-generated strings.
- Domain semantics already covered by other linters (e.g., privilege lint, mypy).

## How to add an invariant-safe exception
- Prefer rewriting the string or condition to avoid the disallowed language.
- If intentional usage is required, add `# invariant-allow: <anchor>` to the relevant line. Anchors should reference `SEMANTIC_GLOSSARY.md` terms when possible (e.g., `# invariant-allow: trust`).
- Keep exceptions narrow: the allow comment only suppresses the specific line it annotates.

## Snapshot regeneration (operator-facing surfaces)
- The snapshot test reads operator-visible strings from `sentient_api.py`, `policy_engine.py`, and `codex/amendments.py` without importing them.
- To accept intentional changes, run:
  - `REGENERATE_OPERATOR_SNAPSHOT=1 python -m scripts.run_tests tests/test_operator_surface_snapshot.py`
- Commit the updated `tests/snapshots/operator_surface.json` after review.
