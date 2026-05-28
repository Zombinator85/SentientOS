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
    assert result.status == "ready"
    assert not result.warning_codes
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


def test_bootstrap_keeps_real_warning_conditions() -> None:
    result = bootstrap_codex_task(
        CodexTaskBootstrapRequest(
            task_name="Codex Task Bootstrapper",
            task_goal="Create deterministic metadata-only bootstrap flow",
            commit_scope="",
            subsystem_kind="developer_workflow_metadata",
            commit_title="[codex:developer] add codex task bootstrapper",
        )
    )
    assert result.status == "ready_with_warnings"
    assert "missing_commit_scope" in result.warning_codes


def test_bootstrap_developer_workflow_metadata_strictness_harmonizer_is_ready() -> None:
    result = bootstrap_codex_task(
        CodexTaskBootstrapRequest(
            task_name="Codex Scaffold Strictness Harmonizer",
            task_goal=(
                "Harmonize scaffold generator, scaffold verifier, preset catalog, and preset verifier "
                "expectations so bootstrap results avoid avoidable ready_with_warnings outcomes caused "
                "only by naming/formatting convention drift."
            ),
            preset_id="developer_workflow_metadata",
            commit_scope="developer",
            subsystem_kind="developer_workflow_metadata",
        )
    )
    assert result.status == "ready"
    assert not result.warning_codes
    assert result.scaffold_verifier_result_summary["forbidden_surface_coverage_ok"] is True


def test_blocked_bootstrap_prompt_is_hard_stop_diagnostic() -> None:
    result = bootstrap_codex_task(
        CodexTaskBootstrapRequest(
            task_name="Network Provider Bootstrap",
            task_goal="add provider network call",
            subsystem_kind="developer_workflow_metadata",
        )
    )
    assert result.status == "blocked"
    assert "BLOCKED_DO_NOT_IMPLEMENT" in result.generated_prompt_text
    assert "implementation contract" in result.generated_prompt_text
    assert "commit with" not in result.generated_prompt_text.lower()
    assert "Only then make_pr" not in result.generated_prompt_text
    assert result.artifact_classification == "diagnostic"
    assert result.generated_scaffold_json["artifact_classification"] == "diagnostic"


def test_ready_with_warnings_still_emits_usable_implementation_prompt() -> None:
    result = bootstrap_codex_task(
        CodexTaskBootstrapRequest(
            task_name="Codex Task Bootstrapper",
            task_goal="Create deterministic metadata-only bootstrap flow",
            commit_scope="",
            subsystem_kind="developer_workflow_metadata",
            commit_title="[codex:developer] add codex task bootstrapper",
        )
    )
    assert result.status == "ready_with_warnings"
    assert result.artifact_classification == "implementation_contract"
    assert "pr_metadata_guard_ready" in result.generated_prompt_text
    assert "Only then make_pr" in result.generated_prompt_text
