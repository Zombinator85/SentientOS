from __future__ import annotations

from sentientos.codex_task_scaffold import CodexTaskScaffoldRequest, build_codex_task_scaffold


def test_minimal_whole_system_ready_or_warn() -> None:
    result = build_codex_task_scaffold(CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="z"))
    assert result.status in {"codex_task_scaffold_ready", "codex_task_scaffold_ready_with_warnings"}
    assert "full relevant validation matrix" in result.scaffold.generated_prompt


def test_missing_metadata_insufficient() -> None:
    result = build_codex_task_scaffold(CodexTaskScaffoldRequest())
    assert result.status == "codex_task_scaffold_insufficient_metadata"


def test_narrow_repair_mode_text() -> None:
    result = build_codex_task_scaffold(CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="z", prompt_mode="narrow_repair"))
    assert "narrow scope" in result.scaffold.generated_prompt.lower() or "narrow repair" in result.scaffold.generated_prompt.lower()


def test_commit_title_warning() -> None:
    result = build_codex_task_scaffold(CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="z", commit_title="bad title"))
    assert "nonconforming_commit_title" in result.scaffold.warning_codes


def test_deterministic_digest() -> None:
    req = CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="z", new_module_path=("b", "a", "a"))
    a = build_codex_task_scaffold(req)
    b = build_codex_task_scaffold(req)
    assert a.scaffold.scaffold_digest == b.scaffold.scaffold_digest
    assert a.scaffold.expected_files == ("a", "b")
