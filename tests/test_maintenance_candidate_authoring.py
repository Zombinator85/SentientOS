from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_candidate_authoring as authoring
from sentientos import maintenance_loop_activation as activation
from sentientos import maintenance_loop_watchdog as watchdog

pytestmark = pytest.mark.no_legacy_skip
NOW = "2030-01-01T12:00:00Z"


def _world(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "repo"; repo.mkdir(); (repo / ".git").mkdir()
    tool = tmp_path / "tool"; tool.write_text("#!/bin/sh\nexit 0\n"); tool.chmod(0o700)
    roots = {name: tmp_path / name for name in ("state", "workspace", "scratch", "inbox")}
    activation.init_roots(repo, roots)
    auth = sorted({"proposal_selection_only", "filesystem_read", "filesystem_write", "code_edit", "test_edit", "validation_execute", "implementation_agent_session", "implementation_process_execute", "implementation_instruction_disclosure", "remote_model_invocation", "repository_state_read", "repository_workspace_provision", "repository_workspace_modify", "repository_commit", "remote_repository_read", "remote_ref_publish", "pull_request_publish"})
    pm: dict[str, object] = {"schema_version": profiles.MANIFEST_SCHEMA, "manifest_id": "pilot", "manifest_digest": "", "template_no_authority": False,
        "repository_identity": "example/repo", "repository_root": str(repo), "base_sha": "a" * 40,
        "allowed_candidate_kinds": ["maintenance_repair"], "allowed_path_prefixes": ["sentientos", "tests"], "forbidden_paths": ["sentientos/private/**"], "authority_classes": auth,
        "budgets": {"maximum_file_count": 8, "maximum_changed_line_count": 500, "maximum_implementation_seconds": 600, "maximum_validation_seconds": 600, "maximum_wall_clock_seconds": 1200, "maximum_attempts": 2, "maximum_corrective_retries": 1, "publication_retry_backoff_seconds": 10, "maximum_actions": 3},
        "operator_reference": "operator:alice", "approval_reference": "approval:1", "not_before": "2030-01-01T00:00:00Z", "expires_at": "2030-01-02T00:00:00Z",
        "state_root": str(roots["state"]), "workspace_root": str(roots["workspace"]), "scratch_root": str(roots["scratch"]), "inbox_root": str(roots["inbox"]), "codex_home": str(tmp_path / "codex-home"),
        "codex_executable": str(tool), "git_executable": str(tool), "python_executable": str(tool),
        "validation_bounds": {"aggregate_validation_ceiling_seconds": 500.0, "per_command_default_ceiling_seconds": 60.0, "terminal_reserve_seconds": 1.0, "heartbeat_interval_seconds": 0.1, "output_tail_limit": 4000, "output_byte_limit": 200000, "maximum_controller_cycles": 2, "require_declared_behavioral_test": True},
        "publication_mode": "pull_request", "remote_name": "origin", "tracked_base_ref": "refs/remotes/origin/main", "base_ref": "refs/heads/main", "head_ref_prefix": "maintenance", "publication_client_executable": str(tool),
        "commit_identity": {"author_name":"Bot","author_email":"bot@example.test","committer_name":"Bot","committer_email":"bot@example.test","reference":"operator:id"}, "commit_title_policy": {"prefix":"[maintenance]"}, "output_directory": str(tmp_path / "bundle")}
    pm["manifest_digest"] = profiles.digest(pm, "manifest_digest"); profile_path = tmp_path / "profile.json"; profile_path.write_bytes(profiles.canonical_bytes(pm) + b"\n"); profiles.render_profile_bundle(profile_path)
    config_path = tmp_path / "bundle" / "maintenance_loop_config.json"
    activation.render_config(config_path, repository_root=repo, state_root=roots["state"], workspace_root=roots["workspace"], scratch_root=roots["scratch"], inbox_root=roots["inbox"],
        standing_grant=tmp_path/"bundle"/profiles.FILENAMES["standing_grant"], selector_policy=tmp_path/"bundle"/profiles.FILENAMES["selector_policy"], foreman_policy=tmp_path/"bundle"/profiles.FILENAMES["foreman_policy"], validation_policy=tmp_path/"bundle"/profiles.FILENAMES["validation_policy"], landing_policy=tmp_path/"bundle"/profiles.FILENAMES["landing_policy"], base_sha="a"*40, tracked_base_ref="refs/remotes/origin/main", implementation_backend="local_codex", commissioned_local_activation=None, maximum_actions=3, maximum_wall_clock_seconds=1200, publication_retry_backoff_seconds=10)
    m: dict[str, object] = {"schema_version": authoring.MANIFEST_SCHEMA, "template_no_authority": False, "manifest_digest": "", "source_reference": "review:1", "repository_identity": "example/repo", "base_sha": "a"*40,
        "objective": "Repair the bounded parser", "bounded_description": "Change one parser and its focused test", "candidate_kind": "maintenance_repair", "severity": "medium", "confidence": "confirmed",
        "subject_paths": ["sentientos/parser.py", "tests/test_parser.py"], "validation_expectations": ["pytest_node:tests/test_parser.py::test_parser"], "evidence_references": ["audit:1"],
        "requested_authority_classes": ["code_edit", "test_edit", "validation_execute"], "constraints": ["no_network", "no_scope_widening"], "estimated_file_count": 2, "estimated_changed_lines": 40,
        "estimated_implementation_seconds": 120, "estimated_validation_seconds": 120, "operator_priority": 10, "activation_profile_bundle_path": str(profile_path), "watchdog_configuration_path": str(config_path), "candidate_inbox_path": str(roots["inbox"]), "intended_output_path": str(tmp_path / "authored")}
    _seal(m); manifest = tmp_path / "candidate-manifest.json"; manifest.write_bytes(authoring.canonical_bytes(m) + b"\n")
    return manifest, m


def _seal(m: dict[str, object]) -> None:
    m["manifest_digest"] = profiles.digest({k: v for k, v in m.items() if k != "manifest_digest"})


def _rewrite(path: Path, m: dict[str, object]) -> None:
    _seal(m); path.write_bytes(authoring.canonical_bytes(m) + b"\n")


def _render(manifest: Path) -> tuple[dict[str, object], Path, Path]:
    result = authoring.render_candidate(manifest)
    return result, Path(str(result["candidate_path"])), Path(str(result["receipt_path"]))


def test_complete_explicit_manifest_renders_verifies_enqueues_and_watchdog_selects(tmp_path: Path) -> None:
    manifest, _ = _world(tmp_path); first, candidate, receipt = _render(manifest); before = (candidate.read_bytes(), receipt.read_bytes()); second, _, _ = _render(manifest)
    assert first["candidate_id"] == second["candidate_id"] and before == (candidate.read_bytes(), receipt.read_bytes())
    verified = authoring.verify_candidate(manifest, candidate, receipt, NOW); assert verified["status"] == "candidate_ready_for_inbox"
    enqueued = authoring.enqueue_candidate(manifest, candidate, receipt, NOW); assert enqueued["status"] == "candidate_enqueued"
    assert authoring.enqueue_candidate(manifest, candidate, receipt, NOW)["write_status"] == "reused"
    cfg = watchdog.load_config(json.loads(manifest.read_text())["watchdog_configuration_path"]); scan = watchdog.scan(cfg, evaluation_time=NOW)
    assert watchdog.decide(cfg, scan)["transition"] == "select_candidate"


@pytest.mark.parametrize(("field", "value", "reason"), [("requested_authority_classes", [], "authority"), ("subject_paths", ["other/file.py"], "path_not_allowed"), ("subject_paths", ["sentientos/private/key.py"], "path_forbidden"), ("base_sha", "b"*40, "base"), ("candidate_kind", "unknown", "kind"), ("estimated_file_count", 9, "file_budget"), ("estimated_changed_lines", 501, "diff_budget"), ("estimated_implementation_seconds", 601, "implementation_budget"), ("estimated_validation_seconds", 601, "validation_budget")])
def test_explicit_scope_authority_identity_kind_and_budgets_fail_closed(tmp_path: Path, field: str, value: object, reason: str) -> None:
    manifest, m = _world(tmp_path); m[field] = value; _rewrite(manifest, m)
    if field == "requested_authority_classes":
        with pytest.raises(ValueError, match="explicit_nonempty"): authoring.render_candidate(manifest)
        return
    _, candidate, receipt = _render(manifest); result = authoring.verify_candidate(manifest, candidate, receipt, NOW)
    assert result["status"] == "candidate_blocked" and reason in " ".join(result["reason_codes"])


def test_schema_non_authority_validation_tampering_symlinks_and_conflicts_block(tmp_path: Path) -> None:
    manifest, m = _world(tmp_path); m["environment"] = {"PATH": "bad"}; _rewrite(manifest, m)
    with pytest.raises(ValueError, match="closed_schema|environment"): authoring.render_candidate(manifest)
    template = tmp_path / "template.json"; authoring.write_candidate_template(template)
    with pytest.raises(ValueError, match="no_authority"): authoring.render_candidate(template)
    manifest, m = _world(tmp_path / "validation"); m["validation_expectations"] = ["shell:rm -rf x"]; _rewrite(manifest, m); _, c, r = _render(manifest)
    assert authoring.verify_candidate(manifest, c, r, NOW)["status"] == "candidate_blocked"
    c.write_bytes(c.read_bytes().replace(b"Repair", b"Alter!", 1)); assert authoring.verify_candidate(manifest, c, r, NOW)["status"] == "candidate_blocked"
    manifest, m = _world(tmp_path / "link"); target = tmp_path / "target"; target.mkdir(); link = tmp_path / "link-out"; link.symlink_to(target, target_is_directory=True); m["intended_output_path"] = str(link); _rewrite(manifest, m)
    with pytest.raises(ValueError, match="symlink"): authoring.render_candidate(manifest)


def test_pilot_plan_is_argv_only_and_inspection_is_review_safe(tmp_path: Path) -> None:
    manifest, _ = _world(tmp_path); _, candidate, receipt = _render(manifest); plan = authoring.print_pilot_plan(manifest, candidate, receipt, NOW)
    assert set(plan["argv"]) == {"doctor_live", "smoke_idle", "verify_candidate", "enqueue_candidate", "run_bounded", "watchdog_inspect", "inspect_base_cursor", "inspect_activation"}
    assert all(isinstance(v, list) for v in plan["argv"].values()) and plan["shell_command"] is None and plan["scheduler_installation"] is False
    inspected = authoring.inspect_candidate(manifest, candidate, receipt, NOW)
    assert inspected["objective"] == "Repair the bounded parser" and "environment" not in json.dumps(inspected).lower()
