from sentientos.codex_finalize_landing import (
    CodexFinalizeLandingArtifactFinding,
    CodexFinalizeLandingCommandResult,
    CodexFinalizeLandingRequest,
    evaluate_finalize_landing,
)


def _ok_cmds() -> tuple[CodexFinalizeLandingCommandResult, ...]:
    return (CodexFinalizeLandingCommandResult("focused_tests", "t", 0),)


def test_pre_commit_ready_to_commit_with_declared_source_changes() -> None:
    req = CodexFinalizeLandingRequest(
        title="x",
        intended_commit_title="x",
        matrix_json_path="/tmp/m.json",
        phase="pre-commit",
        focused_test_commands=("t",),
        changed_files=("sentientos/codex_finalize_landing.py",),
    )
    artifacts = (CodexFinalizeLandingArtifactFinding("sentientos/codex_finalize_landing.py", "intended_task_change", "allow_pre_commit"),)
    res = evaluate_finalize_landing(req, _ok_cmds(), artifacts)
    assert res.decision.status == "ready_to_commit"


def test_pre_commit_blocks_undeclared_source_change() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    artifacts = (CodexFinalizeLandingArtifactFinding("scripts/codex_finalize_landing.py", "source_change_not_declared", "block"),)
    res = evaluate_finalize_landing(req, _ok_cmds(), artifacts)
    assert res.decision.status == "repair_required_task_caused"


def test_pr_metadata_with_source_dirty_blocks() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pr-metadata", focused_test_commands=("t",), changed_files=("a.py",))
    artifacts = (CodexFinalizeLandingArtifactFinding("a.py", "intended_task_change", "block"),)
    res = evaluate_finalize_landing(req, _ok_cmds(), artifacts)
    assert res.decision.status == "repair_required_task_caused"


def test_pr_metadata_clean_ready() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pr-metadata", focused_test_commands=("t",))
    artifacts = (CodexFinalizeLandingArtifactFinding("", "clean", "none"),)
    res = evaluate_finalize_landing(req, _ok_cmds(), artifacts)
    assert res.decision.status == "ready_for_pr_metadata"


def test_pre_commit_ready_with_inferred_source_changes() -> None:
    req = CodexFinalizeLandingRequest(
        title="x",
        intended_commit_title="x",
        matrix_json_path="/tmp/m.json",
        phase="pre-commit",
        focused_test_commands=("t",),
        inferred_changed_files=("docs/development/codex_finalize_landing.md",),
        allow_current_tracked_changes=True,
        dirty_file_classification_source="inferred",
    )
    artifacts = (CodexFinalizeLandingArtifactFinding("docs/development/codex_finalize_landing.md", "intended_task_change", "allow_pre_commit"),)
    res = evaluate_finalize_landing(req, _ok_cmds(), artifacts)
    assert res.decision.status == "ready_to_commit"
