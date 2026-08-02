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


def test_valid_v2_witness_acceptance_reaches_existing_custody_boundary(tmp_path, monkeypatch) -> None:
    """The finalizer consumes the generic verifier result; v2 needs no production special case."""
    import json
    from sentientos.behavioral_witness import build_witness, digest
    from sentientos.task_acceptance import verify
    monkeypatch.setattr("sentientos.task_acceptance.subprocess.run", lambda *a, **k: type("R", (), {"stdout": "sha\n"})())
    node = "tests/test_codex_finalize_landing.py::test_valid_v2_witness_acceptance_reaches_existing_custody_boundary"
    witness = build_witness(repository_sha="sha", run_id="run", node_id=node, contract_id="c", witness_kind="k", facts={"ok": True})
    provenance = {"git_sha":"sha", "run_id":"run", "reporter_ok":True, "metrics_status":"ok",
                  "selected_node_ids":[node], "node_outcomes":[{"node_id":node,"phase":"call","outcome":"passed"}],
                  "behavioral_witnesses":[witness], "behavioral_witness_digest":digest([witness])}
    manifest = {"schema_version":"sentientos.task_acceptance:v2", "repository_sha":"sha", "task_classification":"behavior_adding",
                "required_nodes":[{"node_id":node,"witness_contracts":[{"contract_id":"c","witness_kind":"k","assertions":[{"op":"is_true","path":"/ok"}]}]}],
                "successful_path_nodes":[node]}
    mp, pp = tmp_path/"manifest.json", tmp_path/"provenance.json"
    mp.write_text(json.dumps(manifest)); pp.write_text(json.dumps(provenance))
    assert verify(mp, pp)["status"] == "task_acceptance_ready"


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


def test_pre_commit_ready_with_inferred_untracked_task_files() -> None:
    req = CodexFinalizeLandingRequest(
        title="x",
        intended_commit_title="x",
        matrix_json_path="/tmp/m.json",
        phase="pre-commit",
        focused_test_commands=("t",),
        inferred_untracked_task_files=("tests/test_new_case.py",),
        allow_current_task_files=True,
        dirty_file_classification_source="tracked+untracked_inferred",
    )
    artifacts = (CodexFinalizeLandingArtifactFinding("tests/test_new_case.py", "intended_task_change", "allow_pre_commit"),)
    res = evaluate_finalize_landing(req, _ok_cmds(), artifacts)
    assert res.decision.status == "ready_to_commit"
