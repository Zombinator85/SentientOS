# Codex Task Scaffold Preset Verifier

`sentientos/codex_task_scaffold_preset_verifier.py` validates preset catalog determinism and whole-system contract coverage for scaffold generation.

## API

- `verify_codex_task_scaffold_presets(preset_id: str | None = None)`
  - Verifies required preset IDs exist.
  - Verifies required groups are present for each preset.
  - Verifies required validation/reporting contract items.
  - Verifies whole-system presets keep final matrix/report/title clauses.
  - Verifies generated scaffolds from presets contain doctrine clauses and title discipline.
  - Supports all presets or one preset ID.

## CLI

`PYTHONPATH=. python scripts/verify_codex_task_scaffold_presets.py [--preset-id <id>] [--summary]`

- Default verifies all presets.
- `--preset-id` scopes to one preset.
- Exit code is non-zero when any verification fails.
