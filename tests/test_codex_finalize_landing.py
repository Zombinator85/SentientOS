from sentientos.codex_finalize_landing import (
    CodexFinalizeLandingArtifactFinding,
    CodexFinalizeLandingCommandResult,
    CodexFinalizeLandingRequest,
    HOSTED_REQUIRED_STAGES,
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


def test_administrator_precondition_blocks_as_environment_without_weakening_audit() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    audit = CodexFinalizeLandingCommandResult(
        "strict_audits",
        "python verify_audits.py --strict",
        1,
        "Access denied: run as Administrator to reach protected memory and policy state.",
    )

    res = evaluate_finalize_landing(req, (*_ok_cmds(), audit), ())

    assert res.decision.status == "environment_blocked"
    assert "stage_failed:strict_audits" in res.decision.reasons
    assert "environment_precondition_unavailable:strict_audits:administrator_required" in res.decision.reasons


def test_privileged_checks_can_be_deferred_only_as_explicit_pr_submission_pending() -> None:
    req = CodexFinalizeLandingRequest(
        "x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",),
        defer_privileged_checks_to_hosted=True,
    )
    pending = tuple(
        CodexFinalizeLandingCommandResult(
            stage, "hosted-only", None,
            "pending_required_hosted_administrator_verification", required=True,
        )
        for stage in HOSTED_REQUIRED_STAGES
    )

    result = evaluate_finalize_landing(req, (*_ok_cmds(), *pending), ())

    assert result.decision.status == "ready_for_pr_submission"
    assert set(result.decision.reasons) == {
        f"hosted_verification_pending:{stage}" for stage in HOSTED_REQUIRED_STAGES
    }


def test_hosted_deferral_never_masks_a_failed_test_or_missing_privileged_stage() -> None:
    req = CodexFinalizeLandingRequest(
        "x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",),
        defer_privileged_checks_to_hosted=True,
    )
    pending_audit = CodexFinalizeLandingCommandResult(
        "strict_audits", "hosted-only", None,
        "pending_required_hosted_administrator_verification", required=True,
    )
    failed_test = CodexFinalizeLandingCommandResult("focused_tests", "pytest", 1, "assertion failed")

    result = evaluate_finalize_landing(req, (pending_audit, failed_test), ())

    assert result.decision.status == "repair_required_task_caused"
    assert "hosted_privileged_stage_deferral_incomplete:audit_immutability" in result.decision.reasons
    assert "stage_failed:focused_tests" in result.decision.reasons


def test_administrator_message_in_task_stage_remains_task_failure() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    failed_test = CodexFinalizeLandingCommandResult(
        "focused_tests",
        "python -m scripts.run_tests",
        1,
        "Access denied: run as Administrator to reach protected memory and policy state.",
    )

    res = evaluate_finalize_landing(req, (failed_test,), ())

    assert res.decision.status == "repair_required_task_caused"
    assert res.decision.reasons == ("stage_failed:focused_tests",)


def test_missing_pinned_mypy_toolchain_is_an_environment_blocker() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    mypy = CodexFinalizeLandingCommandResult(
        "mypy_baseline",
        "python scripts/check_mypy_baseline.py",
        2,
        '{"status":"mypy_baseline_toolchain_mismatch","expected_mypy_version":"1.20.2"}',
    )

    res = evaluate_finalize_landing(req, (*_ok_cmds(), mypy), ())

    assert res.decision.status == "environment_blocked"
    assert "stage_failed:mypy_baseline" in res.decision.reasons
    assert "environment_precondition_unavailable:mypy_baseline:pinned_toolchain_missing_or_mismatched" in res.decision.reasons


def test_missing_audit_dependency_and_temporary_storage_are_environment_blockers() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    missing_dependency = CodexFinalizeLandingCommandResult(
        "audit_immutability",
        "python scripts/audit_immutability_verifier.py",
        1,
        "ModuleNotFoundError: No module named 'nacl'",
    )
    unavailable_temp = CodexFinalizeLandingCommandResult(
        "focused_tests",
        "python -m scripts.run_tests",
        1,
        "temporary-storage-unavailable: workspace temp filesystem lacks capacity",
    )
    docs_dependencies = CodexFinalizeLandingCommandResult(
        "docs_check_deps",
        "python scripts/build_docs.py --check-deps",
        1,
        "ENVIRONMENT/BOOTSTRAP ERROR: Docs build dependencies missing.",
    )
    docs_build = CodexFinalizeLandingCommandResult(
        "docs_build",
        "python scripts/build_docs.py",
        2,
        "ENVIRONMENT/BOOTSTRAP ERROR: Docs build dependencies missing.",
    )

    res = evaluate_finalize_landing(req, (*_ok_cmds(), missing_dependency, unavailable_temp, docs_dependencies, docs_build), ())

    assert res.decision.status == "environment_blocked"
    assert "stage_failed:audit_immutability" in res.decision.reasons
    assert "environment_precondition_unavailable:audit_immutability:pynacl_missing" in res.decision.reasons
    assert "environment_precondition_unavailable:focused_tests:temporary_storage" in res.decision.reasons
    assert "environment_precondition_unavailable:docs_check_deps:docs_dependencies_missing" in res.decision.reasons
    assert "environment_precondition_unavailable:docs_build:docs_dependencies_missing" in res.decision.reasons


def test_unclassified_required_stage_failure_remains_task_repair_blocker() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    stage = CodexFinalizeLandingCommandResult("focused_tests", "pytest", 1, "assertion failed")

    res = evaluate_finalize_landing(req, (stage,), ())

    assert res.decision.status == "repair_required_task_caused"
    assert res.decision.reasons == ("stage_failed:focused_tests",)


def test_environment_blocker_does_not_mask_a_task_failure() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    administrator = CodexFinalizeLandingCommandResult(
        "strict_audits", "python verify_audits.py --strict", 1,
        "Access denied: run as Administrator to reach protected memory and policy state.",
    )
    failed_test = CodexFinalizeLandingCommandResult(
        "focused_tests", "pytest", 1, "assertion failed",
    )

    res = evaluate_finalize_landing(req, (*_ok_cmds(), administrator, failed_test), ())

    assert res.decision.status == "repair_required_task_caused"
    assert "environment_precondition_unavailable:strict_audits:administrator_required" in res.decision.reasons
    assert "stage_failed:focused_tests" in res.decision.reasons


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
