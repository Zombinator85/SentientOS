from sentientos.codex_finalize_landing import (
    _ADMINISTRATOR_UNAVAILABLE_PROOF,
    CodexFinalizeLandingArtifactFinding,
    CodexFinalizeLandingCommandResult,
    CodexFinalizeLandingPolicy,
    CodexFinalizeLandingRequest,
    evaluate_finalize_landing,
)
from sentientos.forge_failures import semantic_failure_signature
from sentientos.validation_causality import compare_runs, command_contract_digest, digest_json, environment_digest


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
    assert res.decision.status == "policy_blocked"


def test_pr_metadata_with_source_dirty_blocks() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pr-metadata", focused_test_commands=("t",), changed_files=("a.py",))
    artifacts = (CodexFinalizeLandingArtifactFinding("a.py", "intended_task_change", "block"),)
    res = evaluate_finalize_landing(req, _ok_cmds(), artifacts)
    assert res.decision.status == "policy_blocked"


def test_pr_metadata_clean_ready() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pr-metadata", focused_test_commands=("t",))
    artifacts = (CodexFinalizeLandingArtifactFinding("", "clean", "none"),)
    res = evaluate_finalize_landing(req, _ok_cmds(), artifacts)
    assert res.decision.status == "ready_for_pr_metadata"


def test_privileged_local_checks_pass_keep_ordinary_commit_readiness() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    checks = _ok_cmds() + (
        CodexFinalizeLandingCommandResult("strict_audits", "audit", 0),
        CodexFinalizeLandingCommandResult("audit_immutability", "immutability", 0),
    )
    assert evaluate_finalize_landing(req, checks, ()).decision.status == "ready_to_commit"


def test_genuine_privileged_substrate_unavailability_defers_only_named_stages() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    evidence = {"probe": "administrator_capability", "available": False, "source": "sentientos.admin_utils.is_admin"}
    checks = _ok_cmds() + tuple(
        CodexFinalizeLandingCommandResult(
            stage, stage, 126, availability_status="substrate_unavailable",
            availability_evidence=evidence, availability_proof=_ADMINISTRATOR_UNAVAILABLE_PROOF,
        )
        for stage in ("strict_audits", "audit_immutability")
    )
    result = evaluate_finalize_landing(req, checks, ())
    assert result.decision.status == "ready_to_commit_pending_hosted_validation"
    assert result.decision.deferred_stage_ids == ("strict_audits", "audit_immutability")
    assert result.decision.deferred_stage_reasons


def test_ordinary_command_failure_cannot_be_deferred() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    result = evaluate_finalize_landing(req, _ok_cmds() + (CodexFinalizeLandingCommandResult("focused_tests", "t", 1),), ())
    assert result.decision.status == "validation_failed"
    assert "validation_failed:stage_failed:focused_tests" in result.decision.reasons


def test_fabricated_unavailable_classification_is_rejected() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    forged = CodexFinalizeLandingCommandResult("strict_audits", "audit", 1, availability_status="substrate_unavailable")
    result = evaluate_finalize_landing(req, _ok_cmds() + (forged,), ())
    assert result.decision.status == "validation_failed"
    assert "validation_failed:stage_failed:strict_audits" in result.decision.reasons


def test_only_repository_policy_listed_docs_privilege_checks_can_be_deferred() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    proof = {"probe": "administrator_capability", "available": False, "source": "sentientos.admin_utils.is_admin"}
    docs = tuple(
        CodexFinalizeLandingCommandResult(stage, stage, 126, availability_status="substrate_unavailable", availability_evidence=proof, availability_proof=_ADMINISTRATOR_UNAVAILABLE_PROOF)
        for stage in ("docs_check_deps", "docs_build")
    )
    result = evaluate_finalize_landing(req, _ok_cmds() + docs, ())
    assert result.decision.status == "ready_to_commit_pending_hosted_validation"
    assert result.decision.deferred_stage_ids == ("docs_check_deps", "docs_build")


def test_hosted_evidence_must_bind_every_deferred_stage_to_candidate_sha() -> None:
    req = CodexFinalizeLandingRequest(
        "x", "x", "/tmp/m.json", phase="pr-metadata", focused_test_commands=("t",),
        repository_sha="a" * 40, deferred_stage_ids=("strict_audits", "audit_immutability"),
        hosted_validation_evidence={"status": "hosted_validation_evidence_ready", "candidate_sha": "b" * 40, "verified_stage_ids": ["strict_audits", "audit_immutability"]},
    )
    evidence = {"probe": "administrator_capability", "available": False, "source": "sentientos.admin_utils.is_admin"}
    unavailable = tuple(CodexFinalizeLandingCommandResult(stage, stage, 126, availability_status="substrate_unavailable", availability_evidence=evidence, availability_proof=_ADMINISTRATOR_UNAVAILABLE_PROOF) for stage in req.deferred_stage_ids)
    result = evaluate_finalize_landing(req, _ok_cmds() + unavailable, ())
    assert result.decision.status == "hosted_validation_incomplete"


def test_missing_hosted_evidence_blocks_deferred_post_commit_stages() -> None:
    req = CodexFinalizeLandingRequest(
        "x", "x", "/tmp/m.json", phase="pr-metadata", focused_test_commands=("t",),
        repository_sha="a" * 40, deferred_stage_ids=("strict_audits",),
    )
    unavailable = CodexFinalizeLandingCommandResult("strict_audits", "audit", 126, availability_status="substrate_unavailable", availability_evidence={"probe": "administrator_capability", "available": False, "source": "sentientos.admin_utils.is_admin"}, availability_proof=_ADMINISTRATOR_UNAVAILABLE_PROOF)
    result = evaluate_finalize_landing(req, _ok_cmds() + (unavailable,), ())
    assert result.decision.status == "hosted_validation_incomplete"


def test_exact_bound_hosted_stage_success_allows_post_commit_readiness() -> None:
    sha = "a" * 40
    req = CodexFinalizeLandingRequest(
        "x", "x", "/tmp/m.json", phase="pr-metadata", focused_test_commands=("t",),
        repository_sha=sha, deferred_stage_ids=("strict_audits",),
        candidate_tree_sha="c" * 40,
        hosted_validation_evidence={"status": "hosted_validation_evidence_ready", "candidate_sha": sha, "candidate_tree_sha": "c" * 40, "verified_stage_ids": ["strict_audits"]},
    )
    unavailable = CodexFinalizeLandingCommandResult("strict_audits", "audit", 126, availability_status="substrate_unavailable", availability_evidence={"probe": "administrator_capability", "available": False, "source": "sentientos.admin_utils.is_admin"}, availability_proof=_ADMINISTRATOR_UNAVAILABLE_PROOF)
    result = evaluate_finalize_landing(req, _ok_cmds() + (unavailable,), ())
    assert result.decision.status == "ready_for_pr_metadata"


def test_failed_hosted_stage_does_not_clear_local_unavailability() -> None:
    req = CodexFinalizeLandingRequest(
        "x", "x", "/tmp/m.json", phase="pr-metadata", focused_test_commands=("t",),
        repository_sha="a" * 40, deferred_stage_ids=("strict_audits",),
        hosted_validation_evidence={"status": "hosted_validation_evidence_blocked", "candidate_sha": "a" * 40, "conclusion": "failure", "reasons": ["hosted_validation_stage_not_passed:strict_audits"], "verified_stage_ids": []},
    )
    unavailable = CodexFinalizeLandingCommandResult("strict_audits", "audit", 126, availability_status="substrate_unavailable", availability_evidence={"probe": "administrator_capability", "available": False, "source": "sentientos.admin_utils.is_admin"})
    result = evaluate_finalize_landing(req, _ok_cmds() + (unavailable,), ())
    assert result.decision.status == "hosted_validation_failed"


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


def _causal_evidence(*, candidate_messages: tuple[str, ...] = ("legacy",)):
    base_sha, candidate_sha = "a" * 40, "b" * 40
    workspace = "sha256:" + "c" * 64
    environment = {"python": "3.11", "pytest": "stable"}
    argv = ["python", "-m", "scripts.run_tests", "-q", "tests/test_debt.py::test_legacy"]

    def failures(messages):
        return [{
            "signature": semantic_failure_signature("tests/test_debt.py::test_legacy", "AssertionError", message),
            "nodeid": "tests/test_debt.py::test_legacy", "exception_type": "AssertionError",
            "message": message, "count": 1,
        } for message in messages]

    def run(sha, identity, messages):
        rows = failures(messages)
        return {
            "repository_sha": sha, "workspace_identity": identity,
            "command_contract": {"runner": "scripts.run_tests", "argv": argv},
            "command_contract_digest": command_contract_digest(argv),
            "environment_identity": environment, "environment_digest": environment_digest(environment),
            "complete": True, "exit_code": 1 if rows else 0, "tests_collected": 1,
            "tests_executed": 1, "junit_sha256": "sha256:" + "d" * 64,
            "normalized_failure_multiset": rows,
        }

    evidence = compare_runs(
        immutable_base_sha=base_sha, candidate_sha=candidate_sha,
        candidate_workspace_identity=workspace,
        base_run=run(base_sha, "sha256:" + "1" * 64, ("legacy",)),
        candidate_run=run(candidate_sha, workspace, candidate_messages),
    )
    return base_sha, candidate_sha, workspace, evidence


def _causal_request(*, evidence, base_sha, candidate_sha, workspace, **changes):
    values = dict(
        title="x", intended_commit_title="x", matrix_json_path="/tmp/m.json",
        phase="pre-commit", focused_test_commands=("focused",),
        immutable_base_sha=base_sha, repository_sha=candidate_sha,
        candidate_workspace_identity=workspace, causal_validation_evidence=evidence,
        causal_validation_expected_command_digest=evidence["command_contract_digest"],
        task_acceptance_status="task_acceptance_ready", protected_corridor_status="passed",
        require_causal_validation=True,
    )
    values.update(changes)
    return CodexFinalizeLandingRequest(**values)


def test_matched_broad_failure_is_visible_debt_not_task_caused() -> None:
    base, candidate, workspace, evidence = _causal_evidence()
    broad = CodexFinalizeLandingCommandResult(
        "broad_validation", "scripts.run_tests -q tests/test_debt.py::test_legacy", 1,
        output_tail="FAILED tests/test_debt.py::test_legacy - AssertionError: legacy",
        command_contract_digest=evidence["command_contract_digest"],
    )
    unavailable = {
        "probe": "administrator_capability", "available": False,
        "source": "sentientos.admin_utils.is_admin",
    }
    privileged = tuple(
        CodexFinalizeLandingCommandResult(
            stage, stage, 126, availability_status="substrate_unavailable",
            availability_evidence=unavailable, availability_proof=_ADMINISTRATOR_UNAVAILABLE_PROOF,
        )
        for stage in ("strict_audits", "audit_immutability")
    )
    result = evaluate_finalize_landing(_causal_request(evidence=evidence, base_sha=base, candidate_sha=candidate, workspace=workspace), _ok_cmds() + (broad,) + privileged, ())
    assert result.decision.status == "ready_to_commit_pending_hosted_validation"
    assert result.report.assessments["regression_gate_status"] == "no_regression"
    assert result.report.assessments["repository_health_status"] == "red"


def test_matched_broad_debt_with_all_local_stages_green_reaches_ready_to_commit() -> None:
    base, candidate, workspace, evidence = _causal_evidence()
    broad = CodexFinalizeLandingCommandResult(
        "broad_validation", "scripts.run_tests -q tests/test_debt.py::test_legacy", 1,
        output_tail="FAILED tests/test_debt.py::test_legacy - AssertionError: legacy",
        command_contract_digest=evidence["command_contract_digest"],
    )
    result = evaluate_finalize_landing(
        _causal_request(evidence=evidence, base_sha=base, candidate_sha=candidate, workspace=workspace),
        _ok_cmds() + (broad,),
        (),
    )
    assert result.decision.status == "ready_to_commit"
    assert result.report.assessments["repository_health_status"] == "red"
    assert result.report.assessments["regression_gate_status"] == "no_regression"


def test_new_broad_failure_blocks_and_cannot_net_against_retired_debt() -> None:
    base, candidate, workspace, evidence = _causal_evidence(candidate_messages=("legacy", "new"))
    broad = CodexFinalizeLandingCommandResult("broad_validation", "broad", 1, command_contract_digest=evidence["command_contract_digest"])
    result = evaluate_finalize_landing(_causal_request(evidence=evidence, base_sha=base, candidate_sha=candidate, workspace=workspace), _ok_cmds() + (broad,), ())
    assert result.decision.status == "repair_required_task_caused"
    assert "candidate_regression_detected" in result.decision.reasons


def test_paired_broad_timeout_is_incomplete_and_allows_only_hosted_validation_commit() -> None:
    from sentientos.validation_causality import verify_comparison

    base_sha, candidate_sha, workspace, evidence = _causal_evidence()
    tree_sha = "9" * 40
    base_run = dict(evidence["base_run_provenance"])
    candidate_run = dict(evidence["candidate_run_provenance"])
    for run in (base_run, candidate_run):
        run.update({
            "complete": False, "exit_code": 124, "metrics_status": "timed_out",
            "reporter_ok": False, "run_tests_timeout_seconds": 45,
            "raw_stdout_tail": "....FF", "raw_stderr_tail": "",
        })
    base_run["workspace_identity"] = digest_json({"git_tree_sha": tree_sha})
    base_run["normalized_failure_multiset"] = []
    candidate_run["normalized_failure_multiset"] = []
    evidence.update({
        "base_run_provenance": base_run,
        "candidate_run_provenance": candidate_run,
        "base_run_provenance_digest": digest_json(base_run),
        "candidate_run_provenance_digest": digest_json(candidate_run),
        "base_source_tree_sha": tree_sha,
        "base_failure_multiset": [], "candidate_failure_multiset": [],
        "status": "comparison_incomplete", "reasons": ["base_or_candidate_run_incomplete"],
    })
    evidence.pop("comparison_digest", None)
    from sentientos.validation_causality import digest_json as comparison_digest
    evidence["comparison_digest"] = comparison_digest(evidence)
    assessment = verify_comparison(
        evidence, immutable_base_sha=base_sha, candidate_sha=candidate_sha,
        candidate_workspace_identity=workspace,
    )
    assert assessment["status"] == "comparison_incomplete"
    assert assessment["incomplete_classification"] == "paired_timeout"
    assert "no_regression" != assessment["status"]

    broad = CodexFinalizeLandingCommandResult(
        "broad_validation", "broad", 124,
        command_contract_digest=evidence["command_contract_digest"],
    )
    unavailable = {"probe": "administrator_capability", "available": False, "source": "sentientos.admin_utils.is_admin"}
    privileged = tuple(CodexFinalizeLandingCommandResult(
        stage, stage, 126, availability_status="substrate_unavailable",
        availability_evidence=unavailable, availability_proof=_ADMINISTRATOR_UNAVAILABLE_PROOF,
    ) for stage in ("strict_audits", "audit_immutability"))
    result = evaluate_finalize_landing(
        _causal_request(evidence=evidence, base_sha=base_sha, candidate_sha=candidate_sha, workspace=workspace),
        _ok_cmds() + (broad,) + privileged, (),
    )
    assert result.decision.status == "ready_to_commit_pending_hosted_validation"
    assert "broad_validation" in result.decision.deferred_stage_ids
    assert result.report.assessments["regression_gate_status"] == "comparison_incomplete"


def test_required_unavailable_stage_without_hosted_policy_is_blocked() -> None:
    req = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("t",))
    proof = {"probe": "administrator_capability", "available": False, "source": "sentientos.admin_utils.is_admin"}
    unavailable = CodexFinalizeLandingCommandResult(
        "strict_audits", "audit", 126, availability_status="substrate_unavailable",
        availability_evidence=proof, availability_proof=_ADMINISTRATOR_UNAVAILABLE_PROOF,
    )
    result = evaluate_finalize_landing(req, _ok_cmds() + (unavailable,), (), policy=CodexFinalizeLandingPolicy(hosted_deferrable_stage_ids=()))
    assert result.decision.status == "validation_incomplete"
    assert "stage_unavailable_without_hosted_substitute:strict_audits" in result.decision.reasons[0]


def test_hosted_handoff_does_not_defer_a_new_complete_broad_failure() -> None:
    req = CodexFinalizeLandingRequest(
        "x", "x", "/tmp/m.json", phase="post-commit", focused_test_commands=("t",),
        repository_sha="a" * 40, deferred_stage_ids=("broad_validation",),
        hosted_validation_handoff_authorized=True, candidate_tree_sha="c" * 40,
    )
    broad = CodexFinalizeLandingCommandResult("broad_validation", "broad", 1)
    result = evaluate_finalize_landing(req, _ok_cmds() + (broad,), ())
    assert result.decision.status == "validation_failed"
    assert "validation_failed:stage_failed:broad_validation" in result.decision.reasons


def test_exact_task_acceptance_and_protected_corridor_override_broad_match() -> None:
    base, candidate, workspace, evidence = _causal_evidence()
    broad = CodexFinalizeLandingCommandResult("broad_validation", "broad", 1, command_contract_digest=evidence["command_contract_digest"])
    acceptance = evaluate_finalize_landing(
        _causal_request(evidence=evidence, base_sha=base, candidate_sha=candidate, workspace=workspace, task_acceptance_status="task_acceptance_blocked"),
        _ok_cmds() + (broad,), (),
    )
    assert "validation_failed:task_acceptance_not_ready" in acceptance.decision.reasons
    corridor = evaluate_finalize_landing(
        _causal_request(evidence=evidence, base_sha=base, candidate_sha=candidate, workspace=workspace, protected_corridor_status="regression_detected"),
        _ok_cmds() + (broad,), (),
    )
    assert "protected_corridor_regression_detected" in corridor.decision.reasons


def test_broad_failure_without_bound_causal_comparison_blocks() -> None:
    broad = CodexFinalizeLandingCommandResult("broad_validation", "broad", 1)
    request = CodexFinalizeLandingRequest("x", "x", "/tmp/m.json", phase="pre-commit", focused_test_commands=("focused",), require_causal_validation=True)
    result = evaluate_finalize_landing(request, _ok_cmds() + (broad,), ())
    assert "validation_incomplete:causal_validation_evidence_missing" in result.decision.reasons
    assert "validation_failed:stage_failed:broad_validation" in result.decision.reasons
