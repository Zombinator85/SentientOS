# Codex Task Scaffold Preset Catalog

This metadata-only subsystem defines deterministic preset profiles used by Codex task scaffolding.

## Preset IDs

- metadata_verification
- metadata_index
- metadata_digest
- metadata_attestation
- operator_review_packet
- operator_confirmed_run
- stabilization
- narrow_repair
- developer_workflow_metadata

## API

Module: `sentientos/codex_task_scaffold_presets.py`

- `list_preset_ids()` returns deterministic sorted IDs.
- `get_preset(preset_id)` returns a typed preset.
- `validate_preset_shape(preset)` validates required groups.

## CLI

`python scripts/list_codex_task_scaffold_presets.py`

- Lists preset IDs.
- `--json` emits machine-readable ID payload.
- `--preset-id <id>` emits full preset JSON.

## Integration behavior

`sentientos/codex_task_scaffold.py` applies preset defaults when `subsystem_kind` matches a known preset ID, while allowing explicit request fields to override defaults.
