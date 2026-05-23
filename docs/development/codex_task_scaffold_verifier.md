# Codex Task Scaffold Verifier

`sentientos/codex_task_scaffold_verifier.py` verifies generated scaffold payloads for whole-system doctrine and landing contract completeness.

## Surfaces

- API: `verify_codex_task_scaffold_payload(payload)`
- CLI: `python scripts/verify_codex_task_scaffold.py --scaffold <json> [--summary]`

## Verification checks

- Required whole-system doctrine clauses in generated prompt.
- Required final validation command categories (`scripts.run_tests`, `mypy`).
- Required final report contract items.
- Commit title discipline (`[codex:<subsystem>] ...`).
- Forbidden-surface coverage for Codex/provider invocation boundaries.
