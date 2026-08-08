from __future__ import annotations
from pathlib import Path
import pytest
from sentientos import maintenance_wake_cycle as wake
from tests.test_maintenance_wake_cycle import _configured

pytestmark = pytest.mark.no_legacy_skip

def test_stop_appearing_after_probe_prevents_autonomy(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path)
    def probe(_): (tmp_path/"STOP").touch(); return {"status":"health_probe_findings"}
    monkeypatch.setattr(wake.health,"probe_once",probe); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:pytest.fail("autonomy ran"))
    result=wake.wake_once(cfg); assert result["status"]=="maintenance_wake_paused"; assert result["effect_counts"]["autonomy_cycle_invocations"]==0

def test_crash_after_probe_resumes_from_governed_custody_without_reprobe(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path,sources=1); monkeypatch.setattr(wake.health,"probe_once",lambda c:pytest.fail("duplicate diagnostic")); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:{"status":"autonomy_cycle_completed","receipt":None})
    assert wake.wake_once(cfg)["receipt"]["probe_skip_reason"]=="existing_governed_source"

def test_concurrent_owner_failure_has_zero_effects(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path); monkeypatch.setattr(wake,"_lock",lambda c:(_ for _ in ()).throw(ValueError("wake_lock_unavailable")))
    result=wake.wake_once(cfg); assert result["status"]=="maintenance_wake_blocked"; assert sum(result["effect_counts"].values())==0

def test_completed_downstream_custody_is_continued_not_reprobed(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    cfg=_configured(monkeypatch,tmp_path,action="continue_existing_work"); monkeypatch.setattr(wake.health,"probe_once",lambda c:pytest.fail("duplicate probe")); monkeypatch.setattr(wake.autonomy,"cycle_once",lambda *a,**k:{"status":"autonomy_cycle_idle","receipt":None})
    assert wake.wake_once(cfg)["effect_counts"]["autonomy_cycle_invocations"]==1


def test_production_cli_process_real_failing_pytest_reaches_terminal_wake_receipt(
    tmp_path: Path,
) -> None:
    """One wake CLI owns the real probe, collection, repair, and publication chain."""
    import json
    import os
    import subprocess
    import sys

    from sentientos import maintenance_activation_profiles as profiles
    from sentientos import maintenance_autonomy_cycle as cycle
    from sentientos import maintenance_candidate_collector as collector
    from sentientos import maintenance_health_probe as health
    from sentientos import maintenance_loop_watchdog as watchdog
    from sentientos.maintenance_validation_controller import ValidationPolicy
    from tests.maintenance_watchdog_implementation_fixtures import NOW, setup
    from tests.test_maintenance_activation_profiles import _manifest, _rewrite

    node = "tests/test_health_target.py::test_allowed_text"
    cfg, roots, repo = setup(
        tmp_path,
        closed_loop=True,
        process_real_health=True,
        validation_expectations=[f"pytest_node:{node}"],
    )
    for path in roots["inbox"].glob("*.json"):
        path.unlink()

    validator = tmp_path / "validator.py"
    validator.write_text(
        "#!/usr/bin/env python3\nfrom pathlib import Path\n"
        "raise SystemExit(0 if 'assert True' in Path('tests/test_health_target.py').read_text() else 1)\n"
    )
    validator.chmod(0o755)
    cfg = dict(cfg)
    cfg["validation_policy"] = ValidationPolicy(
        "wake-process-real", "repo", python_executable=str(validator),
        external_scratch_root=str(roots["scratch"]),
        per_command_default_ceiling_seconds=2, maximum_controller_cycles=2,
        maximum_corrective_retries=1,
    ).to_dict()
    cfg["maximum_actions"] = 20
    cfg["stop_marker"] = str(roots["state"] / "STOP")
    policy = cfg["selector_policy"]

    manifest_path, manifest = _manifest(tmp_path / "activation")
    foreman = cfg["foreman_policy"]
    manifest.update({
        "repository_identity": "repo", "repository_root": str(repo),
        "base_sha": cfg["base_sha"],
        "allowed_candidate_kinds": policy["allowed_candidate_kinds"],
        "allowed_path_prefixes": policy["allowed_path_prefixes"],
        "forbidden_paths": policy["forbidden_path_patterns"],
        "authority_classes": policy["available_authority_classes"],
        "not_before": "2026-01-01T00:00:00Z", "expires_at": "2027-01-01T00:00:00Z",
        "state_root": str(roots["state"]), "workspace_root": str(roots["workspace"]),
        "scratch_root": str(roots["scratch"]), "inbox_root": str(roots["inbox"]),
        "codex_home": str(roots["codex_home"]), "codex_executable": foreman["codex_executable"],
        "git_executable": "/usr/bin/git", "python_executable": str(validator),
        "output_directory": str(tmp_path / "profile-bundle"),
        "publication_mode": "fast_forward_base_ref", "remote_name": "origin",
        "tracked_base_ref": "refs/remotes/origin/main", "base_ref": "refs/heads/main",
    })
    manifest["budgets"].update({
        "maximum_file_count": 2, "maximum_changed_line_count": 20,
        "maximum_implementation_seconds": 30, "maximum_validation_seconds": 30,
        "maximum_wall_clock_seconds": 3600, "maximum_attempts": 2,
        "maximum_corrective_retries": 1, "maximum_actions": 20,
        "publication_retry_backoff_seconds": 1,
    })
    _rewrite(manifest_path, manifest)
    assert profiles.render_profile_bundle(manifest_path)["status"] == "profile_bundle_ready"

    cfg = watchdog.validate_config({k: v for k, v in cfg.items() if k != "config_digest"})
    watchdog_path = tmp_path / "watchdog.json"
    watchdog_path.write_text(json.dumps(cfg, sort_keys=True))

    signals = tmp_path / "signals"
    signals.mkdir(mode=0o700)
    probe_state = tmp_path / "probe-state"
    probe_state.mkdir(mode=0o700)
    health_cfg = health.validate_config({
        "schema_version": health.CONFIG_SCHEMA, "repository_identity": "repo",
        "repository_root": str(repo), "base_sha": cfg["base_sha"],
        "pytest_node_ids": [node], "probe_timeout_seconds": 60,
        "maximum_failing_records": 1, "probe_state_root": str(probe_state),
        "governed_signal_output_root": str(signals),
        "declared_validation_expectations": [f"pytest_node:{node}"],
        "requested_maintenance_authority_classes": sorted(policy["available_authority_classes"]),
        "declared_constraints": ["bounded"], "estimated_file_count": 1,
        "estimated_changed_line_count": 10, "estimated_implementation_seconds": 10,
        "estimated_validation_seconds": 10, "evaluation_time": NOW,
        "receipt_journal_path": str(probe_state / "receipts.jsonl"),
    })
    health_path = tmp_path / "health.json"
    health_path.write_text(json.dumps(health_cfg, sort_keys=True))

    collector_state = tmp_path / "collector-state"
    collector_state.mkdir(mode=0o700)
    work_sources = tmp_path / "work-sources"
    work_sources.mkdir(mode=0o700)
    collector_cfg = collector.validate_config({
        "schema_version": collector.CONFIG_SCHEMA, "repository_identity": "repo",
        "repository_root": str(repo), "base_sha": cfg["base_sha"],
        "activation_profile_bundle_manifest_path": str(manifest_path),
        "watchdog_configuration_path": str(watchdog_path),
        "collector_state_root": str(collector_state),
        "maintenance_candidate_inbox": str(roots["inbox"]),
        "governed_improvement_signal_source_roots": [str(signals)],
        "normalized_work_item_source_roots": [str(work_sources)],
        "allowed_source_schemas": [collector.GOVERNED_SIGNAL_SCHEMA],
        "allowed_source_kinds": ["governed_improvement_signal"],
        "maximum_source_records_per_scan": 2, "maximum_candidates_per_collection": 1,
        "maximum_input_bytes_per_record": 100000, "evaluation_time_required": True,
        "receipt_journal_path": str(collector_state / "receipts.jsonl"),
        "stop_marker": str(collector_state / "STOP"),
    })
    collector_path = tmp_path / "collector.json"
    collector_path.write_text(json.dumps(collector_cfg, sort_keys=True))

    cycle_state = tmp_path / "cycle-state"
    cycle_state.mkdir(mode=0o700)
    cycle_cfg = cycle.validate_config({
        "schema_version": cycle.CONFIG_SCHEMA, "repository_identity": "repo",
        "repository_root": str(repo), "base_sha": cfg["base_sha"],
        "activation_profile_bundle_manifest_path": str(manifest_path),
        "collector_configuration_path": str(collector_path),
        "watchdog_configuration_path": str(watchdog_path),
        "external_cycle_state_root": str(cycle_state),
        "cycle_receipt_journal_path": str(cycle_state / "receipts.jsonl"),
        "stop_marker": str(cycle_state / "STOP"), "maximum_cycle_wall_clock_seconds": 60,
        "maximum_collector_invocations_per_cycle": 1,
        "maximum_watchdog_invocations_per_cycle": 1,
        "maximum_candidates_collected_per_cycle": 1,
        "remote_readiness_probe_required": False, "evaluation_time_required": True,
    })
    cycle_path = tmp_path / "cycle.json"
    cycle_path.write_text(json.dumps(cycle_cfg, sort_keys=True))

    wake_state = tmp_path / "wake-state"
    wake_state.mkdir(mode=0o700)
    wake_cfg = wake.validate_config({
        "schema_version": wake.CONFIG_SCHEMA, "repository_identity": "repo",
        "repository_root": str(repo), "base_sha": cfg["base_sha"],
        "health_probe_configuration_path": str(health_path),
        "autonomy_cycle_configuration_path": str(cycle_path),
        "external_wake_state_root": str(wake_state),
        "wake_receipt_journal_path": str(wake_state / "receipts.jsonl"),
        "stop_marker": str(wake_state / "STOP"), "evaluation_time": NOW,
    })
    wake_path = tmp_path / "wake.json"
    wake_path.write_text(json.dumps(wake_cfg, sort_keys=True))
    env = dict(os.environ, FAKE_CODEX_MODE="corrective",
               FAKE_CODEX_TARGET="tests/test_health_target.py",
               FAKE_CODEX_CONTENT="def test_allowed_text():\n    assert 0\n",
               FAKE_CODEX_CORRECTIVE_CONTENT="def test_allowed_text():\n    assert True\n",
               PYTHONPATH=str(Path.cwd()))
    process = subprocess.run(
        [sys.executable, "scripts/maintenance_wake_cycle.py", "--config", str(wake_path), "--evaluation-time", "2026-08-08T12:34:56.0000000Z", "wake-once"],
        cwd=Path.cwd(), env=env, text=True, capture_output=True, timeout=90, check=False,
    )
    assert process.returncode == 0, process.stderr + process.stdout
    result = json.loads(process.stdout.splitlines()[-1])
    assert result["status"] == "autonomy_cycle_completed", result
    assert result["effect_counts"] == {"health_probe_invocations": 1, "autonomy_cycle_invocations": 1}

    provenance = json.loads((repo / "glow/test_runs/test_run_provenance.json").read_text())
    assert provenance["selected_node_ids"] == [node]
    assert provenance["tests_executed"] == provenance["tests_failed"] == 1
    assert provenance["pytest_exit_code"] == 1
    failure = json.loads((repo / "glow/test_runs/test_failure_digest.json").read_text())
    assert failure["failure_groups"][0]["example_nodeid"].endswith("::test_allowed_text")
    assert health.inspect(health_cfg)["receipt_count"] == 1
    assert len(list(signals.glob("health-probe-*.json"))) == 1
    assert len((collector_state / "receipts.jsonl").read_text().splitlines()) == 1
    assert len(list(roots["inbox"].glob("*.json"))) == 1

    watchdog_result = result["receipt"]["autonomy_cycle_result"]["watchdog_result"]
    assert [tick["transition"] for tick in watchdog_result["ticks"]] == [
        "select_candidate", "admit_candidate", "prepare_implementation",
        "start_implementation", "observe_process", "validate", "commit_enqueue",
        "publish", "close_task", "idle",
    ]
    state = roots["state"]
    expected = {"maintenance_leases": 1, "maintenance_agent_sessions": 1,
                "maintenance_validation_results": 2, "maintenance_commit_results": 1,
                "maintenance_publication_results": 1}
    for directory, count in expected.items():
        assert len(list((state / directory).glob("*.json"))) == count
    invocations = [json.loads(path.read_text()) for path in (state / "maintenance_codex_invocations").glob("*.json")]
    assert len(invocations) == 2
    assert len({item["session_id"] for item in invocations}) == 1

    commit = json.loads(next((state / "maintenance_commit_results").glob("*.json")).read_text())
    publication = json.loads(next((state / "maintenance_publication_results").glob("*.json")).read_text())
    remote = subprocess.run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=repo,
                            text=True, capture_output=True, check=True).stdout.split()[0]
    assert remote == commit["commit_sha"] == publication["commit_sha"]
    assert all(publication[key] is False for key in (
        "force_push_used", "merge_performed", "hosted_checks_waited",
        "credential_bytes_inspected", "operator_message_relayed"))
    assert sum(tick["transition"] == "close_task" for tick in watchdog_result["ticks"]) == 1
    assert watchdog_result["ticks"][-1]["transition"] == "idle"

    receipt = result["receipt"]
    assert receipt["health_probe_result"]["governed_signal_path"]
    assert receipt["autonomy_cycle_result"]["receipt"]["receipt_digest"]
    custody = receipt["terminal_custody"]
    assert custody == receipt["autonomy_cycle_result"]["receipt"]["terminal_custody"]
    assert custody["commit_sha"] == remote
    assert custody["publication_id"] == publication["publication_id"]
    assert custody["closure_event_id"].startswith("mevent_")
    assert wake.inspect_receipts(wake_cfg)["status"] == "receipts_ready"
    assert wake.inspect_receipts(wake_cfg)["receipt_count"] == 1
    assert not any(path.name == "candidate.json" for path in roots["inbox"].glob("*.json"))
    assert not (wake_state / "STOP").exists()
