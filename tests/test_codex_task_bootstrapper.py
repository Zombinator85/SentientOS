from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task


def test_bootstrap_ready_and_metadata_only_boundaries() -> None:
    result = bootstrap_codex_task(
        CodexTaskBootstrapRequest(
            task_name="Codex Task Bootstrapper",
            task_goal="Create deterministic metadata-only bootstrap flow",
            subsystem_kind="developer_workflow_metadata",
            commit_title="[codex:developer] add codex task bootstrapper",
        )
    )
    assert result.status in {"ready", "ready_with_warnings"}
    assert "no codex invocation" in result.explicit_non_authority_boundaries
    assert "module_path" in result.planned_paths
    assert result.generated_prompt_text


def test_bootstrap_blocks_for_forbidden_authority_request() -> None:
    result = bootstrap_codex_task(
        CodexTaskBootstrapRequest(
            task_name="Network Provider Bootstrap",
            task_goal="add provider network call",
            subsystem_kind="developer_workflow_metadata",
        )
    )
    assert result.status == "blocked"
    assert "forbidden_authority_surface_requested" in result.blocker_codes
