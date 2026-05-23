from __future__ import annotations

from sentientos.codex_task_scaffold import CodexTaskScaffoldRequest, build_codex_task_scaffold
from sentientos.codex_task_scaffold_presets import get_preset, list_preset_ids, validate_preset_shape


def test_preset_ids_deterministic() -> None:
    ids = list_preset_ids()
    assert ids == tuple(sorted(ids))
    assert "developer_workflow_metadata" in ids


def test_get_preset_and_shape() -> None:
    preset = get_preset("developer_workflow_metadata")
    assert preset.preset_id == "developer_workflow_metadata"
    assert validate_preset_shape(preset) == ()


def test_scaffold_uses_preset_defaults() -> None:
    result = build_codex_task_scaffold(
        CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="developer_workflow_metadata")
    )
    assert "typed_metadata_api" in result.scaffold.final_report_contract or "module_api_summary" in result.scaffold.final_report_contract
    assert "runtime_authority_expansion" in result.scaffold.forbidden_surfaces
