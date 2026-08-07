from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sentientos import governed_improvement_signal_plane as signal_plane
from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_autonomy_cycle as cycle
from sentientos import maintenance_candidate_collector as collector
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos.maintenance_validation_controller import ValidationPolicy
from tests.maintenance_watchdog_implementation_fixtures import NOW, setup
from tests.test_maintenance_activation_profiles import _manifest, _rewrite

pytestmark = pytest.mark.no_legacy_skip


def test_production_cli_process_real_governed_signal_cycle_reaches_publication_and_idle(
    tmp_path: Path,
) -> None:
    cfg, roots, repo = setup(
        tmp_path,
        closed_loop=True,
        validation_expectations=["pytest_node:tests/fake.py::test_corrected"],
    )
    # The shared watchdog fixture supplies a candidate for watchdog-only tests.
    # This proof permits only the candidate produced by the governed collector.
    for path in roots["inbox"].glob("*.json"):
        path.unlink()

    validator = tmp_path / "validator.py"
    validator.write_text(
        "#!/usr/bin/env python3\nfrom pathlib import Path\n"
        "raise SystemExit(0 if Path('allowed.txt').read_text() == 'corrected\\n' else 1)\n"
    )
    validator.chmod(0o755)
    cfg = dict(cfg)
    cfg["validation_policy"] = ValidationPolicy(
        "closed-loop",
        "repo",
        python_executable=str(validator),
        external_scratch_root=str(roots["scratch"]),
        per_command_default_ceiling_seconds=2,
        maximum_controller_cycles=2,
        maximum_corrective_retries=1,
    ).to_dict()
    cfg["maximum_actions"] = 20

    cycle_root = tmp_path / "cycle-state"
    cycle_root.mkdir(mode=0o700)
    stop_marker = cycle_root / "STOP"
    cfg["stop_marker"] = str(roots["state"] / "STOP")

    manifest_path, manifest = _manifest(tmp_path / "activation")
    policy = cfg["selector_policy"]
    foreman = cfg["foreman_policy"]
    manifest.update(
        {
            "repository_identity": "repo",
            "repository_root": str(repo),
            "base_sha": cfg["base_sha"],
            "allowed_candidate_kinds": policy["allowed_candidate_kinds"],
            "allowed_path_prefixes": policy["allowed_path_prefixes"],
            "forbidden_paths": policy["forbidden_path_patterns"],
            "authority_classes": policy["available_authority_classes"],
            "not_before": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "state_root": str(roots["state"]),
            "workspace_root": str(roots["workspace"]),
            "scratch_root": str(roots["scratch"]),
            "inbox_root": str(roots["inbox"]),
            "codex_home": str(roots["codex_home"]),
            "codex_executable": foreman["codex_executable"],
            "git_executable": "/usr/bin/git",
            "python_executable": str(validator),
            "output_directory": str(tmp_path / "profile-bundle"),
            "publication_mode": "fast_forward_base_ref",
            "remote_name": "origin",
            "tracked_base_ref": "refs/remotes/origin/main",
            "base_ref": "refs/heads/main",
        }
    )
    manifest["budgets"].update(
        {
            "maximum_file_count": 2,
            "maximum_changed_line_count": 20,
            "maximum_implementation_seconds": 30,
            "maximum_validation_seconds": 30,
            "maximum_wall_clock_seconds": 3600,
            "maximum_attempts": 2,
            "maximum_corrective_retries": 1,
            "maximum_actions": 20,
            "publication_retry_backoff_seconds": 1,
        }
    )
    _rewrite(manifest_path, manifest)
    assert profiles.render_profile_bundle(manifest_path)["status"] == "profile_bundle_ready"

    cfg = watchdog.validate_config({k: v for k, v in cfg.items() if k != "config_digest"})
    watchdog_path = tmp_path / "watchdog.json"
    watchdog_path.write_text(json.dumps(cfg, sort_keys=True))

    source_root = tmp_path / "sources"
    source_root.mkdir()
    work_root = tmp_path / "work-sources"
    work_root.mkdir()
    signal = signal_plane.normalize_record(
        {
            "source_kind": "run_tests",
            "finding_kind": "code",
            "severity": "high",
            "description": "Change allowed.txt deterministically",
            "subject_path": "allowed.txt",
            "source_artifact": "failure.json",
            "source_digest": "sha256:" + "1" * 64,
            "evidence_refs": ["operator:test"],
            "declared_validation_expectations": ["pytest_node:tests/fake.py::test_corrected"],
            "requested_authority_classes": policy["available_authority_classes"],
            "declared_constraints": ["bounded"],
            "estimated_file_count": 1,
            "estimated_changed_line_count": 10,
            "estimated_implementation_seconds": 10,
            "estimated_validation_seconds": 10,
        },
        repo_root=repo,
    )
    evaluation = signal_plane.evaluate_signal_plane([signal], repo_root=repo)
    (source_root / "signal.json").write_text(json.dumps(evaluation.to_dict(), sort_keys=True))

    collector_state = tmp_path / "collector-state"
    collector_state.mkdir(mode=0o700)
    collector_cfg = collector.validate_config(
        {
            "schema_version": collector.CONFIG_SCHEMA,
            "repository_identity": "repo",
            "repository_root": str(repo),
            "base_sha": cfg["base_sha"],
            "activation_profile_bundle_manifest_path": str(manifest_path),
            "watchdog_configuration_path": str(watchdog_path),
            "collector_state_root": str(collector_state),
            "maintenance_candidate_inbox": str(roots["inbox"]),
            "governed_improvement_signal_source_roots": [str(source_root)],
            "normalized_work_item_source_roots": [str(work_root)],
            "allowed_source_schemas": [collector.GOVERNED_SIGNAL_SCHEMA],
            "allowed_source_kinds": ["governed_improvement_signal"],
            "maximum_source_records_per_scan": 2,
            "maximum_candidates_per_collection": 1,
            "maximum_input_bytes_per_record": 100000,
            "evaluation_time_required": True,
            "receipt_journal_path": str(collector_state / "receipts.jsonl"),
            "stop_marker": str(collector_state / "STOP"),
        }
    )
    collector_path = tmp_path / "collector.json"
    collector_path.write_text(json.dumps(collector_cfg, sort_keys=True))

    cycle_cfg = cycle.validate_config(
        {
            "schema_version": cycle.CONFIG_SCHEMA,
            "repository_identity": "repo",
            "repository_root": str(repo),
            "base_sha": cfg["base_sha"],
            "activation_profile_bundle_manifest_path": str(manifest_path),
            "collector_configuration_path": str(collector_path),
            "watchdog_configuration_path": str(watchdog_path),
            "external_cycle_state_root": str(cycle_root),
            "cycle_receipt_journal_path": str(cycle_root / "receipts.jsonl"),
            "stop_marker": str(stop_marker),
            "maximum_cycle_wall_clock_seconds": 30,
            "maximum_collector_invocations_per_cycle": 1,
            "maximum_watchdog_invocations_per_cycle": 1,
            "maximum_candidates_collected_per_cycle": 1,
            "remote_readiness_probe_required": False,
            "evaluation_time_required": True,
        }
    )
    cycle_path = tmp_path / "cycle.json"
    cycle_path.write_text(json.dumps(cycle_cfg, sort_keys=True))

    env = dict(os.environ, FAKE_CODEX_MODE="corrective", PYTHONPATH=str(Path.cwd()))
    process = subprocess.run(
        [
            sys.executable,
            "scripts/maintenance_autonomy_cycle.py",
            "--config",
            str(cycle_path),
            "--evaluation-time",
            NOW,
            "cycle-once",
        ],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stderr + process.stdout
    result = json.loads(process.stdout)
    assert result["status"] == "autonomy_cycle_completed"
    assert result["effect_counts"] == {
        "collector_invocations": 1,
        "watchdog_invocations": 1,
        "candidates_collected": 1,
    }
    assert [tick["transition"] for tick in result["watchdog_result"]["ticks"]] == [
        "select_candidate", "admit_candidate", "prepare_implementation",
        "start_implementation", "observe_process", "validate", "commit_enqueue",
        "publish", "close_task", "idle",
    ]

    state = roots["state"]
    expected_counts = {
        "maintenance_leases": 1,
        "maintenance_agent_sessions": 1,
        "maintenance_validation_results": 2,
        "maintenance_commit_results": 1,
        "maintenance_publication_results": 1,
    }
    for directory, count in expected_counts.items():
        assert len(list((state / directory).glob("*.json"))) == count
    assert len(list(roots["inbox"].glob("*.json"))) == 1
    assert len(list(source_root.glob("*.json"))) == 1
    assert len(list((state / "maintenance_codex_invocations").glob("*.json"))) == 2
    sessions = {
        json.loads(path.read_text())["session_id"]
        for path in (state / "maintenance_codex_invocations").glob("*.json")
    }
    assert sessions == {
        json.loads(next((state / "maintenance_agent_sessions").glob("*.json")).read_text())["session_id"]
    }
    publication = next(
        tick["effect_result"] for tick in result["watchdog_result"]["ticks"]
        if tick["transition"] == "publish"
    )
    assert all(
        publication[key] is False
        for key in (
            "force_push_used", "merge_performed", "hosted_checks_waited",
            "credential_bytes_inspected", "operator_message_relayed",
        )
    )
    remote = subprocess.run(
        ["git", "ls-remote", "origin", "refs/heads/main"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split()[0]
    assert remote != cfg["base_sha"]
    assert result["receipt"]["terminal_status"] == "autonomy_cycle_completed"
    custody = result["receipt"]["terminal_custody"]
    lease = json.loads(next((state / "maintenance_leases").glob("*.json")).read_text())
    session = json.loads(next((state / "maintenance_agent_sessions").glob("*.json")).read_text())
    commit = json.loads(next((state / "maintenance_commit_results").glob("*.json")).read_text())
    published = json.loads(next((state / "maintenance_publication_results").glob("*.json")).read_text())
    assert custody["task_id"] == lease["task_id"]
    assert (custody["lease_id"], custody["lease_digest"]) == (lease["lease_id"], lease["lease_digest"])
    assert (custody["attempt_id"], custody["implementation_session_id"]) == (session["attempt_id"], session["session_id"])
    assert custody["implementation_thread_id"] == "thread-ok"
    assert {item["terminal_status"] for item in custody["validation_results"]} == {
        "validation_failed_correctable", "validation_ready_for_commit",
    }
    assert (custody["commit_result_id"], custody["commit_sha"]) == (commit["commit_result_id"], commit["commit_sha"])
    assert custody["publication_id"] == published["publication_id"]
    assert custody["base_cursor_before"] == cfg["base_sha"]
    assert custody["base_cursor_after"] == remote == commit["commit_sha"]
    assert custody["closure_event_id"].startswith("mevent_")
    terminal_tick = result["watchdog_result"]["ticks"][-1]
    assert terminal_tick["transition"] == terminal_tick["status"] == "idle"
    assert terminal_tick["effect_result"] == {"status": "idle"}
    assert cycle.inspect_receipts(cycle_cfg)["status"] == "receipts_ready"
    assert not stop_marker.exists()


def test_explicit_watchdog_status_mapping_never_calls_waiting_complete() -> None:
    assert cycle._map_watchdog({"status": "waiting", "ticks": []}, had_candidate=True) == "autonomy_cycle_waiting"
    assert cycle._map_watchdog({"status": "blocked", "ticks": []}, had_candidate=True) == "autonomy_cycle_blocked"
    assert cycle._map_watchdog({"status": "paused", "ticks": []}, had_candidate=True) == "autonomy_cycle_paused"


def test_completion_requires_close_then_idle() -> None:
    result = {"status": "idle", "ticks": [{"transition": "close_task", "status": "completed"}, {"transition": "idle", "status": "idle"}]}
    assert cycle._map_watchdog(result, had_candidate=True) == "autonomy_cycle_completed"
    assert cycle._map_watchdog({"status": "idle", "ticks": []}, had_candidate=True) == "autonomy_cycle_idle"
