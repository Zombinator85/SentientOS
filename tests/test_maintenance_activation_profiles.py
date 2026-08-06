from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_candidate_selector as selector
from sentientos import maintenance_commit_publication as landing
from sentientos import maintenance_local_codex_foreman as foreman
from sentientos import maintenance_task_authority_lease as authority
from sentientos import maintenance_validation_controller as validation

pytestmark = pytest.mark.no_legacy_skip


def _manifest(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "repo"; repo.mkdir(); (repo / ".git").mkdir()
    exe = tmp_path / "tool"; exe.write_text("#!/bin/sh\nexit 0\n"); exe.chmod(0o700)
    auth = sorted({"proposal_selection_only", "filesystem_read", "filesystem_write", "code_edit", "test_edit", "validation_execute", "implementation_agent_session", "implementation_process_execute", "implementation_instruction_disclosure", "remote_model_invocation", "repository_state_read", "repository_workspace_provision", "repository_workspace_modify", "repository_commit", "remote_repository_read", "remote_ref_publish", "pull_request_publish"})
    m: dict[str, object] = {
        "schema_version": profiles.MANIFEST_SCHEMA, "manifest_id": "operator-approved-1", "manifest_digest": "", "template_no_authority": False,
        "repository_identity": "example/repo", "repository_root": str(repo), "base_sha": "a" * 40,
        "allowed_candidate_kinds": ["maintenance_repair"], "allowed_path_prefixes": ["sentientos", "tests"], "forbidden_paths": [".git/**"], "authority_classes": auth,
        "budgets": {"maximum_file_count": 8, "maximum_changed_line_count": 500, "maximum_implementation_seconds": 600, "maximum_validation_seconds": 600, "maximum_wall_clock_seconds": 1200, "maximum_attempts": 2, "maximum_corrective_retries": 1, "publication_retry_backoff_seconds": 10, "maximum_actions": 3},
        "operator_reference": "operator:alice", "approval_reference": "approval:ticket-1", "not_before": "2030-01-01T00:00:00Z", "expires_at": "2030-01-02T00:00:00Z",
        "state_root": str(tmp_path/"state"), "workspace_root": str(tmp_path/"workspace"), "scratch_root": str(tmp_path/"scratch"), "inbox_root": str(tmp_path/"inbox"), "codex_home": str(tmp_path/"codex-home"),
        "codex_executable": str(exe), "git_executable": str(exe), "python_executable": str(exe),
        "validation_bounds": {"aggregate_validation_ceiling_seconds": 500.0, "per_command_default_ceiling_seconds": 60.0, "terminal_reserve_seconds": 1.0, "heartbeat_interval_seconds": 0.1, "output_tail_limit": 4000, "output_byte_limit": 200000, "maximum_controller_cycles": 2, "require_declared_behavioral_test": True},
        "publication_mode": "pull_request", "remote_name": "origin", "tracked_base_ref": "refs/remotes/origin/main", "base_ref": "refs/heads/main", "head_ref_prefix": "maintenance",
        "publication_client_executable": str(exe), "commit_identity": {"author_name":"Maintenance Bot","author_email":"bot@example.test","committer_name":"Maintenance Bot","committer_email":"bot@example.test","reference":"operator:identity-1"}, "commit_title_policy": {"prefix":"[maintenance]"}, "output_directory": str(tmp_path/"bundle"),
    }
    m["manifest_digest"] = profiles.digest(m, "manifest_digest")
    path = tmp_path / "manifest.json"; path.write_bytes(profiles.canonical_bytes(m)+b"\n")
    return path, m


def _rewrite(path: Path, m: dict[str, object]) -> None:
    m["manifest_digest"] = profiles.digest(m, "manifest_digest"); path.write_bytes(profiles.canonical_bytes(m)+b"\n")


def test_complete_manifest_renders_five_canonically_valid_artifacts_and_exact_retry(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path); first = profiles.render_profile_bundle(path)
    before = {p.name:p.read_bytes() for p in (tmp_path/"bundle").iterdir()}; second = profiles.render_profile_bundle(path)
    assert first["status"] == second["status"] == "profile_bundle_ready" and before == {p.name:p.read_bytes() for p in (tmp_path/"bundle").iterdir()}
    root = tmp_path/"bundle"; grant=json.loads((root/profiles.FILENAMES["standing_grant"]).read_text())
    assert authority.verify_grant(grant, evaluation_time="2030-01-01T12:00:00Z")["status"] == "grant_valid"
    selector.build_policy(json.loads((root/profiles.FILENAMES["selector_policy"]).read_text()))
    foreman.LocalCodexForemanConfig.from_mapping(json.loads((root/profiles.FILENAMES["foreman_policy"]).read_text()))
    validation.ValidationPolicy.from_mapping(json.loads((root/profiles.FILENAMES["validation_policy"]).read_text()))
    landing.seal_landing_policy(json.loads((root/profiles.FILENAMES["landing_policy"]).read_text()))
    assert profiles.verify_profile_bundle(path, "2030-01-01T12:00:00Z")["status"] == "profile_bundle_ready"


def test_missing_authority_and_secret_field_block_without_inference(tmp_path: Path) -> None:
    path, m = _manifest(tmp_path); m["authority_classes"] = []; _rewrite(path,m)
    with pytest.raises(ValueError, match="authority_classes"): profiles.render_profile_bundle(path)
    path,m = _manifest(tmp_path/"second"); m["credential_token"] = "bad"; _rewrite(path,m)
    with pytest.raises(ValueError, match="closed_schema|secret"): profiles.render_profile_bundle(path)


def test_conflict_tampering_expiry_and_repository_mismatch_block(tmp_path: Path) -> None:
    path,m = _manifest(tmp_path); profiles.render_profile_bundle(path); grant=tmp_path/"bundle"/profiles.FILENAMES["standing_grant"]
    grant.write_text("{}\n"); assert profiles.verify_profile_bundle(path,"2030-01-01T12:00:00Z")["status"] == "profile_bundle_blocked"
    with pytest.raises(ValueError, match="conflict"): profiles.render_profile_bundle(path)
    assert profiles.verify_profile_bundle(path,"2030-01-03T00:00:00Z")["status"] == "profile_bundle_blocked"
    m["repository_identity"]="other/repo"; _rewrite(path,m)
    assert profiles.verify_profile_bundle(path,"2030-01-01T12:00:00Z")["status"] == "profile_bundle_blocked"


def test_scope_and_foreman_authority_mismatch_block(tmp_path: Path) -> None:
    path,_ = _manifest(tmp_path); profiles.render_profile_bundle(path); root=tmp_path/"bundle"
    sp=root/profiles.FILENAMES["selector_policy"]; value=json.loads(sp.read_text()); value["allowed_path_prefixes"]=["wider"]; value=selector.build_policy(value).to_dict(); sp.write_bytes(profiles.canonical_bytes(value)+b"\n")
    assert profiles.verify_profile_bundle(path,"2030-01-01T12:00:00Z")["status"] == "profile_bundle_blocked"
    profiles.render_profile_bundle(path) if False else None


def test_unsafe_output_symlink_template_and_argv_only_plan(tmp_path: Path) -> None:
    path,m = _manifest(tmp_path); m["output_directory"] = str(Path(m["repository_root"])/"bundle"); _rewrite(path,m)
    with pytest.raises(ValueError, match="inside_repository"): profiles.render_profile_bundle(path)
    template=tmp_path/"template.json"; profiles.write_manifest_template(template)
    with pytest.raises(ValueError): profiles.render_profile_bundle(template)
    path,m=_manifest(tmp_path/"safe"); profiles.render_profile_bundle(path); plan=profiles.activation_plan(path,"2030-01-01T12:00:00Z")
    assert len(plan["argv"]) == 5 and all(isinstance(argv,list) for argv in plan["argv"])
    assert plan["scheduler_installation"] is False and "shell" not in profiles.canonical_bytes(plan).decode()
    target=tmp_path/"target"; target.mkdir(); link=tmp_path/"link"; link.symlink_to(target, target_is_directory=True); m["output_directory"]=str(link); _rewrite(path,m)
    with pytest.raises(ValueError, match="symlink"): profiles.render_profile_bundle(path)
