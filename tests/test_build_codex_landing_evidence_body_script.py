from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sentientos.codex_pr_landing_gate import verify_pr_landing_gate
from sentientos.codex_pr_metadata_contract import REQUIRED_BODY_MARKERS, verify_pr_metadata
from sentientos.landing_validation_plan import seal_validation_plan
from scripts.build_codex_landing_evidence_body import main

TITLE = "[codex:landing] harden evidence and recovery rail"
pytestmark = pytest.mark.no_legacy_skip


def _matrix(path: Path) -> Path:
    payload = {
        "status": "passed",
        "required_failure_count": 0,
        "command_count": 8,
        "required_failures": [],
        "results": [
            {"label": "targeted_tests", "command": ["python", "-m", "scripts.run_tests", "-q", "tests/test_build_codex_landing_evidence_body_script.py"], "required": True, "exit_code": 0},
            {"label": "targeted_mypy", "command": ["python", "-m", "mypy", "scripts/build_codex_landing_evidence_body.py"], "required": True, "exit_code": 0},
            {"label": "mypy_baseline", "command": ["python", "scripts/check_mypy_baseline.py"], "required": True, "exit_code": 0},
            {"label": "docs_check_deps", "command": ["python", "scripts/build_docs.py", "--check-deps"], "required": False, "exit_code": 0},
            {"label": "docs_build", "command": ["python", "scripts/build_docs.py"], "required": True, "exit_code": 0},
            {"label": "prompt_boundaries", "command": ["python", "scripts/verify_context_hygiene_prompt_boundaries.py"], "required": True, "exit_code": 0},
            {"label": "strict_audits", "command": ["python", "verify_audits.py", "--strict"], "required": True, "exit_code": 0},
            {"label": "audit_immutability", "command": ["python", "scripts/audit_immutability_verifier.py"], "required": True, "exit_code": 0},
        ],
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _finalizer(path: Path, profile: str = "exhaustive") -> Path:
    matrix_status = "matrix_passed" if profile == "exhaustive" else "not_requested_for_solo_profile"
    plan = seal_validation_plan({"requested_profile": profile, "effective_profile": profile, "exhaustive_matrix_status": matrix_status, "required_stage_ids": [], "stage_results": {}})
    commands = [
        {"stage": stage, "command": stage, "exit_code": 0, "required": True}
        for stage in ("mypy_baseline", "prompt_boundary", "strict_audits", "audit_immutability")
    ]
    path.write_text(json.dumps({"decision": {"status": "ready_for_pr_metadata"}, "report": {"commands": commands}, "commit_binding": {}, "landing_validation_plan": plan}, sort_keys=True), encoding="utf-8")
    return path


def _build(tmp_path: Path) -> Path:
    matrix = _matrix(tmp_path / "matrix.json")
    supervisor = tmp_path / "supervisor.json"
    supervisor.write_text(json.dumps({"decision": {"status": "ready_for_pr_metadata"}, "report": {"reasons": []}}, sort_keys=True), encoding="utf-8")
    output = tmp_path / "body.txt"
    finalizer = _finalizer(tmp_path / "finalizer.json")
    code = main(
        [
            "--title",
            TITLE,
            "--intended-commit-title",
            TITLE,
            "--matrix-json-path",
            str(matrix),
            "--landing-supervisor-json-path",
            str(supervisor),
            "--output",
            str(output),
            "--pr-metadata-finalizer-json-path",
            str(finalizer),
            "--targeted-mypy",
            "passed",
            "--baseline",
            "passed",
            "--docs-build",
            "passed",
            "--prompt-boundary",
            "passed",
            "--strict-audit",
            "passed",
            "--immutability-verifier",
            "passed",
            "--landing-gate",
            "passed",
            "--finalizer",
            "pre-commit ready_to_commit; post-commit ready_for_pr_metadata",
            "--pr-metadata-guard",
            "pr_metadata_guard_ready",
            "--unresolved-risks",
            "None known.",
        ]
    )
    assert code == 0
    return output


def test_generated_body_includes_matrix_output_path(tmp_path: Path) -> None:
    output = _build(tmp_path)
    assert f"Matrix output path: {tmp_path / 'matrix.json'}" in output.read_text(encoding="utf-8")


def test_generated_body_includes_unresolved_risks(tmp_path: Path) -> None:
    body = _build(tmp_path).read_text(encoding="utf-8")
    assert "### Unresolved risks" in body
    assert "Unresolved risks: None known." in body


def test_generated_body_includes_every_pr_metadata_guard_required_marker(tmp_path: Path) -> None:
    body = _build(tmp_path).read_text(encoding="utf-8")
    result = verify_pr_metadata(pr_title=TITLE, intended_commit_title=TITLE, pr_body=body)
    assert result.status == "codex_pr_metadata_contract_ready"
    for marker in REQUIRED_BODY_MARKERS:
        assert marker in " ".join(body.lower().split())


def test_missing_matrix_json_fails(tmp_path: Path) -> None:
    output = tmp_path / "body.txt"
    code = main(["--title", TITLE, "--intended-commit-title", TITLE, "--matrix-json-path", str(tmp_path / "missing.json"), "--landing-supervisor-json-path", str(tmp_path / "supervisor.json"), "--output", str(output), "--pr-metadata-finalizer-json-path", str(_finalizer(tmp_path / "finalizer.json"))])
    assert code == 1
    assert not output.exists()


def test_missing_matrix_path_marker_fails(tmp_path: Path) -> None:
    from scripts.build_codex_landing_evidence_body import validate_body

    matrix = _matrix(tmp_path / "matrix.json")
    body = _build(tmp_path).read_text(encoding="utf-8").replace(f"Matrix output path: {matrix}", "Matrix output path omitted")
    try:
        validate_body(body, validation_profile="exhaustive", matrix_json_path=matrix)
    except ValueError as exc:
        assert "Matrix output path" in str(exc)
    else:
        raise AssertionError("validate_body accepted a body without the matrix path marker")


def test_generated_body_passes_landing_gate_without_matrix_output_reference_missing(tmp_path: Path) -> None:
    matrix = _matrix(tmp_path / "matrix.json")
    body = _build(tmp_path).read_text(encoding="utf-8")
    result = verify_pr_landing_gate(proposed_pr_title=TITLE, intended_commit_title=TITLE, proposed_pr_body=body, matrix_json_text=matrix.read_text(encoding="utf-8"))
    assert result.decision == "pr_metadata_allowed"
    assert "matrix_output_reference_missing" not in result.blocker_codes


def test_script_is_deterministic(tmp_path: Path) -> None:
    first = _build(tmp_path).read_text(encoding="utf-8")
    second = _build(tmp_path).read_text(encoding="utf-8")
    assert first == second


def test_contradictory_stale_and_ready_markers_fail(tmp_path: Path) -> None:
    output = tmp_path / "body.txt"
    matrix = _matrix(tmp_path / "matrix.json")
    supervisor = tmp_path / "supervisor.json"
    supervisor.write_text(json.dumps({"decision": {"status": "ready_for_pr_metadata"}, "report": {"reasons": []}}, sort_keys=True), encoding="utf-8")
    finalizer = _finalizer(tmp_path / "finalizer.json")
    code = main(
        [
            "--title",
            TITLE,
            "--intended-commit-title",
            TITLE,
            "--matrix-json-path",
            str(matrix),
            "--landing-supervisor-json-path",
            str(supervisor),
            "--output",
            str(output),
            "--pr-metadata-finalizer-json-path",
            str(finalizer),
            "--finalizer",
            "ready_for_pr_metadata but stale_evidence_matrix_output remains",
            "--pr-metadata-guard",
            "pr_metadata_guard_ready",
            "--unresolved-risks",
            "None known.",
        ]
    )
    assert code == 1
    assert not output.exists()


def test_generated_pr_evidence_includes_bound_acceptance_result(tmp_path: Path) -> None:
    matrix = _matrix(tmp_path / "matrix.json")
    supervisor = tmp_path / "supervisor.json"
    supervisor.write_text(json.dumps({"decision": {"status": "ready_for_pr_metadata"}}, sort_keys=True), encoding="utf-8")
    finalizer = tmp_path / "finalizer.json"
    plan = seal_validation_plan({"requested_profile": "exhaustive", "effective_profile": "exhaustive", "exhaustive_matrix_status": "matrix_passed", "required_stage_ids": [], "stage_results": {}})
    finalizer.write_text(json.dumps({"decision": {"status": "ready_for_pr_metadata"}, "commit_binding": {}, "landing_validation_plan": plan, "task_acceptance": {"status": "task_acceptance_ready", "manifest_digest": "sha256:manifest", "provenance_digest": "sha256:provenance", "required_node_ids": ["tests/test_x.py::test_ok"], "successful_path_node_ids": ["tests/test_x.py::test_ok"], "node_outcomes": [{"node_id": "tests/test_x.py::test_ok", "outcome": "passed"}]}}, sort_keys=True), encoding="utf-8")
    output = tmp_path / "body.txt"
    assert main(["--title", TITLE, "--intended-commit-title", TITLE, "--matrix-json-path", str(matrix), "--landing-supervisor-json-path", str(supervisor), "--output", str(output), "--pr-metadata-finalizer-json-path", str(finalizer)]) == 0
    body = output.read_text(encoding="utf-8")
    assert "task_acceptance_ready" in body
    assert "sha256:manifest" in body
    assert "sha256:provenance" in body


def test_solo_generation_without_matrix_is_truthful_and_binds(tmp_path: Path) -> None:
    finalizer = _finalizer(tmp_path / "solo-finalizer.json", "solo")
    output = tmp_path / "solo-body.md"
    sidecar = tmp_path / "solo-binding.json"
    code = main([
        "--title", TITLE, "--intended-commit-title", TITLE,
        "--landing-supervisor-json-path", "",
        "--output", str(output),
        "--pr-metadata-finalizer-json-path", str(finalizer),
        "--sidecar-output", str(sidecar), "--verify-body-binding",
    ])
    assert code == 0
    body = output.read_text(encoding="utf-8")
    assert "Validation profile: solo" in body
    assert "not_requested_for_solo_profile" in body
    assert "See exact task acceptance and phase-finalizer checks below" in body
    assert "Targeted mypy result: not recorded in matrix or finalizer" in body
    assert "Docs build result: not recorded in matrix or finalizer" in body
    assert "Baseline result: passed by finalizer (exit_code=0)" in body
    assert "Prompt-boundary result: passed by finalizer (exit_code=0)" in body
    assert "Strict audit result: passed by finalizer (exit_code=0)" in body
    assert "Immutability verifier result: passed by finalizer (exit_code=0)" in body
    assert "Landing Supervisor result: not required by the sealed solo validation profile." in body
    assert "pending or not yet written at ." not in body
    assert "matrix runner succeeded" not in body.lower()


def test_hosted_pending_plans_are_supported_and_body_prohibits_merge(monkeypatch, tmp_path: Path) -> None:
    from sentientos.codex_finalize_landing import (
        HOSTED_QUALITY_GATE_CONTEXT,
        HOSTED_QUALITY_GATE_INTEGRATION_ID,
        HOSTED_REQUIRED_STAGES,
    )

    hosted = {
        "status": "pending", "required": True,
        "required_check_context": HOSTED_QUALITY_GATE_CONTEXT,
        "required_check_integration_id": HOSTED_QUALITY_GATE_INTEGRATION_ID,
        "pending_stages": list(HOSTED_REQUIRED_STAGES), "merge_permitted": False,
    }
    common = {
        "requested_profile": "solo", "effective_profile": "solo", "title": TITLE,
        "intended_commit_title": TITLE, "task_acceptance_manifest_digest": None,
        "task_acceptance_provenance_digest": None,
        "focused_test_command_contract": [], "targeted_mypy_command_contract": [],
        "hosted_verification": hosted, "required_stage_ids": list(HOSTED_REQUIRED_STAGES),
        "stage_results": {stage: {"status": "deferred_to_hosted"} for stage in HOSTED_REQUIRED_STAGES},
        "exhaustive_matrix_status": "not_requested_for_solo_profile",
        "overall_status": "ready_for_pr_submission",
    }
    pre_plan = seal_validation_plan({**common, "phase": "pre-commit"})
    post_plan = seal_validation_plan({**common, "phase": "pr-metadata"})
    pre = tmp_path / "pre.json"
    post = tmp_path / "post.json"
    guard = tmp_path / "guard.json"
    pre.write_text(json.dumps({"decision": {"status": "ready_for_pr_submission"}, "landing_validation_plan": pre_plan, "workspace_binding": {}, "commit_binding": {}}))
    post.write_text(json.dumps({"decision": {"status": "ready_for_pr_submission"}, "landing_validation_plan": post_plan, "commit_binding": {}}))
    guard.write_text(json.dumps({"status": "pr_metadata_guard_ready_for_submission", "proof": {"hosted_verification": {key: hosted[key] for key in ("status", "required_check_context", "required_check_integration_id", "merge_permitted")}}}))
    calls = []

    def verify_transition(*args, hosted_verification_pending=False, **kwargs):
        calls.append(hosted_verification_pending)
        return True, (), {"hosted_verification_pending": hosted_verification_pending, "merge_permitted": not hosted_verification_pending}

    monkeypatch.setattr("scripts.build_codex_landing_evidence_body.verify_validation_plan_transition", verify_transition)
    output = tmp_path / "body.md"
    assert main([
        "--title", TITLE, "--intended-commit-title", TITLE,
        "--landing-supervisor-json-path", "", "--output", str(output),
        "--pre-commit-finalizer-json-path", str(pre),
        "--pr-metadata-finalizer-json-path", str(post),
        "--pr-metadata-guard-json-path", str(guard),
        "--finalizer", "ready_for_pr_submission", "--pr-metadata-guard", "pr_metadata_guard_ready_for_submission",
        "--strict-audit", "pending in hosted gate", "--immutability-verifier", "pending in hosted gate",
        "--unresolved-risks", "Do not merge until the required hosted check passes.",
    ]) == 0
    body = output.read_text()
    assert calls == [True]
    assert "### Hosted verification" in body
    assert "merge_permitted` is false" in body
    assert "matrix passed" not in body.lower()


def test_unsupplied_motivation_does_not_claim_unrelated_work(tmp_path: Path) -> None:
    finalizer = _finalizer(tmp_path / "solo-finalizer.json", "solo")
    output = tmp_path / "body.md"
    code = main([
        "--title", TITLE, "--intended-commit-title", TITLE,
        "--landing-supervisor-json-path", "", "--output", str(output),
        "--pr-metadata-finalizer-json-path", str(finalizer),
    ])
    assert code == 0
    body = output.read_text(encoding="utf-8")
    assert "Motivation was not supplied to the evidence-body generator." in body
    assert "Harden Codex landing evidence" not in body


def test_solo_rejects_supplied_exhaustive_matrix(tmp_path: Path) -> None:
    output = tmp_path / "body.md"
    code = main([
        "--title", TITLE, "--intended-commit-title", TITLE,
        "--matrix-json-path", str(_matrix(tmp_path / "matrix.json")),
        "--landing-supervisor-json-path", "", "--output", str(output),
        "--pr-metadata-finalizer-json-path", str(_finalizer(tmp_path / "solo.json", "solo")),
    ])
    assert code == 1
    assert not output.exists()


def test_exhaustive_without_matrix_fails_closed(tmp_path: Path) -> None:
    output = tmp_path / "body.md"
    code = main([
        "--title", TITLE, "--intended-commit-title", TITLE,
        "--landing-supervisor-json-path", "", "--output", str(output),
        "--pr-metadata-finalizer-json-path", str(_finalizer(tmp_path / "exhaustive.json")),
    ])
    assert code == 1
    assert not output.exists()


def test_body_builder_accepts_verified_task_acceptance_source_rollforward(tmp_path: Path) -> None:
    base_sha = "1" * 40
    head_sha = "2" * 40
    node_id = "tests/test_build_codex_landing_evidence_body_script.py::test_body_builder_accepts_verified_task_acceptance_source_rollforward"
    common = {
        "requested_profile": "solo",
        "effective_profile": "solo",
        "title": TITLE,
        "intended_commit_title": TITLE,
        "focused_test_command_contract": ["python -m scripts.run_tests -q tests/test_build_codex_landing_evidence_body_script.py"],
        "targeted_mypy_command_contract": ["python -m mypy scripts/build_codex_landing_evidence_body.py"],
        "exhaustive_matrix_status": "not_requested_for_solo_profile",
        "required_stage_ids": [],
        "stage_results": {},
    }

    def acceptance(repository_sha: str, manifest_digest: str, provenance_digest: str) -> dict[str, object]:
        return {
            "status": "task_acceptance_ready",
            "task_classification": "behavior_adding",
            "repository_sha": repository_sha,
            "manifest_digest": manifest_digest,
            "provenance_digest": provenance_digest,
            "required_node_ids": [node_id],
            "successful_path_node_ids": [node_id],
            "node_outcomes": [{"node_id": node_id, "exists": True, "selected": True, "phase": "call", "outcome": "passed", "passed": True}],
            "witness_status": "ready",
            "required_witness_contract_count": 0,
            "passed_witness_contract_count": 0,
            "witness_contract_results": [],
        }

    pre_acceptance = acceptance(base_sha, "sha256:pre-manifest", "sha256:pre-provenance")
    post_acceptance = acceptance(head_sha, "sha256:post-manifest", "sha256:post-provenance")
    pre_plan = seal_validation_plan({
        **common, "repository_sha": base_sha, "phase": "pre-commit",
        "overall_status": "ready_to_commit",
        "task_acceptance_manifest_digest": pre_acceptance["manifest_digest"],
        "task_acceptance_provenance_digest": pre_acceptance["provenance_digest"],
    })
    post_plan = seal_validation_plan({
        **common, "repository_sha": head_sha, "phase": "pr-metadata",
        "overall_status": "ready_for_pr_metadata",
        "task_acceptance_manifest_digest": post_acceptance["manifest_digest"],
        "task_acceptance_provenance_digest": post_acceptance["provenance_digest"],
    })
    changed_manifest_digest = "sha256:changed-paths"
    pre_path = tmp_path / "pre.json"
    pre_path.write_text(json.dumps({
        "decision": {"status": "ready_to_commit"},
        "landing_validation_plan": pre_plan,
        "workspace_binding": {
            "base_head_sha": base_sha, "intended_commit_title": TITLE,
            "changed_path_manifest_digest": changed_manifest_digest, "matrix_digest": "",
        },
        "task_acceptance": pre_acceptance,
    }), encoding="utf-8")
    post_path = tmp_path / "post.json"
    post_path.write_text(json.dumps({
        "decision": {"status": "ready_for_pr_metadata"},
        "landing_validation_plan": post_plan,
        "commit_binding": {
            "parent_sha": base_sha, "head_sha": head_sha, "commit_subject": TITLE,
            "changed_path_manifest_digest": changed_manifest_digest, "matrix_digest": "",
            "tree_sha": "3" * 40,
        },
        "task_acceptance": post_acceptance,
    }), encoding="utf-8")
    guard_path = tmp_path / "guard.json"
    guard_path.write_text(json.dumps({"status": "pr_metadata_guard_ready"}), encoding="utf-8")
    gate_path = tmp_path / "landing-gate.json"
    gate_path.write_text(json.dumps({
        "status": "codex_pr_landing_gate_ready",
        "decision": "pr_metadata_allowed",
        "blocker_codes": [],
        "warning_codes": [],
    }), encoding="utf-8")
    output = tmp_path / "body.md"
    sidecar = tmp_path / "binding.json"

    code = main([
        "--title", TITLE, "--intended-commit-title", TITLE,
        "--landing-supervisor-json-path", "", "--output", str(output),
        "--pre-commit-finalizer-json-path", str(pre_path),
        "--pr-metadata-finalizer-json-path", str(post_path),
        "--pr-metadata-guard-json-path", str(guard_path),
        "--pr-metadata-guard", "pr_metadata_guard_ready; unverified caller note",
        "--landing-gate-json-path", str(gate_path),
        "--sidecar-output", str(sidecar), "--verify-body-binding",
    ])

    assert code == 0
    body = output.read_text(encoding="utf-8")
    assert "task_acceptance_ready" in body
    assert "sha256:post-manifest" in body
    assert "Finalizer artifact status: ready_to_commit; ready_for_pr_metadata." in body
    assert "PR metadata guard artifact status: pr_metadata_guard_ready" in body
    assert "Landing gate artifact decision: pr_metadata_allowed" in body
    assert "unverified caller note" not in body
    assert "pending standard two-phase finalizer" not in body
    assert "pending post-commit finalizer evidence" not in body
    binding = json.loads(sidecar.read_text(encoding="utf-8"))
    assert binding["body_sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert binding["body_byte_length"] == len(body.encode("utf-8"))

    for index, claim in enumerate(("blocked", "not pr_metadata_guard_ready")):
        contradictory_output = tmp_path / f"contradictory-{index}.md"
        rejected = main([
            "--title", TITLE, "--intended-commit-title", TITLE,
            "--landing-supervisor-json-path", "", "--output", str(contradictory_output),
            "--pre-commit-finalizer-json-path", str(pre_path),
            "--pr-metadata-finalizer-json-path", str(post_path),
            "--pr-metadata-guard-json-path", str(guard_path),
            "--pr-metadata-guard", claim,
        ])
        assert rejected == 1
        assert not contradictory_output.exists()
