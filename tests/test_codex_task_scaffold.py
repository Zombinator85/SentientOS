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


def test_generated_prompt_includes_two_phase_finalizer_rules() -> None:
    result = build_codex_task_scaffold(CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="z"))
    prompt = result.scaffold.generated_prompt
    assert "ready_to_commit" in prompt
    assert "ready_for_pr_metadata" in prompt
    assert "do not commit or make_pr" in prompt


def test_preset_final_report_contract_includes_finalizer_results() -> None:
    result = build_codex_task_scaffold(CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="developer_workflow_metadata"))
    contract = result.scaffold.final_report_contract
    assert "pre_commit_finalizer_result" in contract
    assert "post_commit_pr_metadata_finalizer_result" in contract
    assert "pr_metadata_result" in contract
