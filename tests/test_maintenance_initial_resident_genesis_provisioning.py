from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sentientos import maintenance_initial_resident_genesis_provisioning as genesis


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()


def manifest(tmp_path: Path) -> dict[str, object]:
    repo=tmp_path/"checkout"; repo.mkdir()
    _run(repo,"init","-b","work"); _run(repo,"config","user.name","Operator"); _run(repo,"config","user.email","operator@example.invalid")
    for name, body in {"sentientosd.py":"# inert test entrypoint\n","scripts/run_tests.py":"# runner surface\n","scripts/maintenance_loop_watchdog.py":"# watchdog cli\n","tests/test_smoke.py":"def test_smoke():\n    pass\n"}.items():
        path=repo/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(body)
    _run(repo,"add","."); _run(repo,"commit","-m","initial")
    sha=_run(repo,"rev-parse","HEAD"); external=tmp_path/"external"
    codex=tmp_path/"codex"; codex.write_text("#!/bin/sh\necho 'usage exec resume jsonl --cwd sandbox final output schema stdin prompt session thread'\n"); codex.chmod(0o700)
    root=lambda name: str(external/name)
    value: dict[str, object]={"schema_version":genesis.MANIFEST_SCHEMA,"manifest_id":"operator-genesis-001","manifest_digest":"",
        "repository_identity":repo.name,"repository_root":str(repo.resolve()),"base_sha":sha,"base_ref":"refs/heads/work","tracked_base_ref":"refs/heads/work",
        "python_executable":str(Path(sys.executable).resolve()),"git_executable":str(Path(subprocess.run(["which","git"],capture_output=True,text=True,check=True).stdout.strip()).resolve()),
        "codex_executable":str(codex.resolve()),"codex_home":root("codex-home"),"provisioning_root":root("provisioning"),"profile_output_root":root("profile"),
        "state_root":root("state"),"workspace_root":root("workspace"),"scratch_root":root("scratch"),"inbox_root":root("inbox"),"collector_state_root":root("collector"),
        "autonomy_state_root":root("autonomy"),"wake_state_root":root("wake"),"cadence_state_root":root("cadence"),"health_state_root":root("health"),"health_signal_root":root("signals"),
        "governed_improvement_signal_source_roots":[root("signals")],"normalized_work_item_source_roots":[root("work-items")],
        "operator_reference":"operator:integration","approval_reference":"approval:profile:001","not_before":"2026-01-01T00:00:00Z","expires_at":"2027-01-01T00:00:00Z",
        "candidate_kinds":["maintenance"],"allowed_path_prefixes":["sentientos"],"forbidden_paths":[".git/**"],
        "authority_classes":["code_edit","filesystem_read","filesystem_write","implementation_agent_session","implementation_instruction_disclosure","implementation_process_execute","journal_read","local_repository_base_advance","repository_commit","repository_state_read","repository_workspace_modify","repository_workspace_provision","validation_execute"],
        "budgets":{"maximum_file_count":10,"maximum_changed_line_count":1000,"maximum_implementation_seconds":600,"maximum_validation_seconds":600,"maximum_wall_clock_seconds":1800,"maximum_attempts":1,"maximum_corrective_retries":0,"publication_retry_backoff_seconds":1,"maximum_actions":1},
        "validation_bounds":{"aggregate_validation_ceiling_seconds":600,"per_command_default_ceiling_seconds":300,"terminal_reserve_seconds":30,"heartbeat_interval_seconds":5,"output_tail_limit":100,"output_byte_limit":100000,"maximum_controller_cycles":1,"require_declared_behavioral_test":True},
        "publication_mode":"local_fast_forward_base_ref","remote_name":"","head_ref_prefix":"operator/","publication_client_executable":str(Path(subprocess.run(["which","git"],capture_output=True,text=True,check=True).stdout.strip()).resolve()),
        "commit_identity":{"author_name":"Operator","author_email":"operator@example.invalid","committer_name":"Operator","committer_email":"operator@example.invalid","reference":"operator:integration"},"commit_title_policy":{"prefix":"[maintenance]"},
        "implementation_backend":"local_codex","maintenance_bounds":{"maximum_actions":1,"maximum_wall_clock_seconds":600,"publication_retry_backoff_seconds":1},
        "collector":{"allowed_source_schemas":["governed_improvement_signal_plane_evaluation:v1","sentientos.normalized_work_item_packet:v1"],"allowed_source_kinds":["governed_improvement_signal","normalized_work_item"],"maximum_source_records_per_scan":10,"maximum_candidates_per_collection":1,"maximum_input_bytes_per_record":100000},
        "health_probe":{"pytest_node_ids":["tests/test_smoke.py::test_smoke"],"probe_timeout_seconds":60,"maximum_failing_records":1,"declared_validation_expectations":["pytest"],"requested_maintenance_authority_classes":["code_edit"],"declared_constraints":["bounded"],"estimated_file_count":1,"estimated_changed_line_count":1,"estimated_implementation_seconds":1,"estimated_validation_seconds":1},
        "autonomy":{"maximum_cycle_wall_clock_seconds":600},"wake":{},"wake_daemon":{"enabled":True,"cadence_interval_seconds":60,"schedule_anchor_utc":"2026-06-01T00:00:00Z","initial_run_posture":"after_interval","maximum_cycles":10,"maximum_daemon_wall_clock_seconds":600,"shutdown_timeout_seconds":5.0},
        "commissioning":{"custody_root":root("commissioning-custody"),"approval_evidence_path":root("operator-approval.json"),"lineage_id":"operator-lineage-001","created_at":"2026-06-01T00:00:00Z","stop_marker":root("commissioning-stop"),"environment_allowlist":["HOME","PATH"],"required_environment":{},"maximum_handoffs":1,"maximum_successful_transitions":1,"maximum_wall_clock_seconds":600,"quiescence_timeout_seconds":5,"readiness_timeout_seconds":5,"launch_timeout_seconds":5}}
    value["manifest_digest"]=genesis.digest(value,"manifest_digest"); return value


def test_fresh_local_only_graph_reaches_commissioning_ready(tmp_path: Path) -> None:
    value=manifest(tmp_path); repo=Path(str(value["repository_root"]))
    assert subprocess.run(["git","remote","get-url","origin"],cwd=repo).returncode != 0
    assert subprocess.run(["git","show-ref","--verify","refs/heads/main"],cwd=repo).returncode != 0
    assert genesis.doctor(value)["status"] == "genesis_provisioning_ready"
    result=genesis.render(value)
    assert result["status"] == "genesis_provisioning_verified"
    assert result["checks"]["commissioning"] == "initial_resident_commissioning_ready"
    assert result["runtime_effects_performed"] is result["resident_launched"] is result["generation_zero_created"] is False
    assert not Path(str(value["commissioning"]["custody_root"])).exists()  # type: ignore[index]
    assert genesis.render(value)["commissioning_inputs"] == result["commissioning_inputs"]


@pytest.mark.parametrize(("mutation","reason"),[
    (lambda m: m.update(base_ref="refs/heads/missing",tracked_base_ref="refs/heads/missing"),"selected_ref_mismatch"),
    (lambda m: m.update(repository_identity=""),"repository_identity_invalid"),
    (lambda m: m.update(tracked_base_ref="refs/heads/other"),"local_base_ref_mismatch"),
    (lambda m: m.update(authority_classes=[*m["authority_classes"],"remote_repository_read"]),"remote_authority_in_local_mode"),
])
def test_manifest_failures(tmp_path: Path, mutation: object, reason: str) -> None:
    value=manifest(tmp_path); mutation(value)  # type: ignore[operator]
    value["manifest_digest"]=genesis.digest(value,"manifest_digest")
    assert genesis.doctor(value)["reason_codes"] == [reason]


def test_conflicting_rerender_and_bundle_tamper_fail_closed(tmp_path: Path) -> None:
    value=manifest(tmp_path); genesis.render(value)
    profile=Path(str(value["profile_output_root"]))/"selector_policy.json"; profile.write_text("{}\n")
    with pytest.raises(ValueError,match="profile_output_conflict"): genesis.render(value)
