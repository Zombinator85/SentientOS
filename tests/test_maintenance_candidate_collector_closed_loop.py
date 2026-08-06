from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.maintenance_candidate_collector import main as collector_main
from scripts.maintenance_loop_watchdog import main as watchdog_main
from sentientos import governed_improvement_signal_plane as signal_plane
from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_candidate_collector as collector
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos.maintenance_validation_controller import ValidationPolicy
from tests.maintenance_watchdog_implementation_fixtures import NOW, setup
from tests.test_maintenance_activation_profiles import _manifest, _rewrite

pytestmark = pytest.mark.no_legacy_skip


def test_process_real_governed_source_to_fake_publication_reaches_idle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg, roots, repo = setup(tmp_path, closed_loop=True,
        validation_expectations=["pytest_node:tests/fake.py::test_corrected"])
    # setup's candidate represents the forbidden operator relay; remove it before
    # producing the one canonical governed source revision.
    for path in roots["inbox"].glob("*.json"):
        path.unlink()
    validator = tmp_path / "validator.py"
    validator.write_text("#!/usr/bin/env python3\nfrom pathlib import Path\nraise SystemExit(0 if Path('allowed.txt').read_text() == 'corrected\\n' else 1)\n")
    validator.chmod(0o755)
    cfg = dict(cfg)
    cfg["validation_policy"] = ValidationPolicy("closed-loop", "repo",
        python_executable=str(validator), external_scratch_root=str(roots["scratch"]),
        per_command_default_ceiling_seconds=2, maximum_controller_cycles=2,
        maximum_corrective_retries=1).to_dict()
    cfg["maximum_actions"] = 20

    manifest_path, manifest = _manifest(tmp_path / "activation")
    policy = cfg["selector_policy"]
    foreman = cfg["foreman_policy"]
    manifest.update({
        "repository_identity": "repo", "repository_root": str(repo), "base_sha": cfg["base_sha"],
        "allowed_candidate_kinds": policy["allowed_candidate_kinds"],
        "allowed_path_prefixes": policy["allowed_path_prefixes"], "forbidden_paths": policy["forbidden_path_patterns"],
        "authority_classes": policy["available_authority_classes"], "not_before": "2026-01-01T00:00:00Z", "expires_at": "2027-01-01T00:00:00Z",
        "state_root": str(roots["state"]), "workspace_root": str(roots["workspace"]), "scratch_root": str(roots["scratch"]),
        "inbox_root": str(roots["inbox"]), "codex_home": str(roots["codex_home"]),
        "codex_executable": foreman["codex_executable"], "git_executable": "/usr/bin/git",
        "python_executable": str(validator), "output_directory": str(tmp_path / "profile-bundle"),
        "publication_mode": "fast_forward_base_ref", "remote_name": "origin",
        "tracked_base_ref": "refs/remotes/origin/main", "base_ref": "refs/heads/main",
    })
    budgets = manifest["budgets"]
    budgets.update({"maximum_file_count": 2, "maximum_changed_line_count": 20, "maximum_implementation_seconds": 30,
                    "maximum_validation_seconds": 30, "maximum_wall_clock_seconds": 3600, "maximum_attempts": 2,
                    "maximum_corrective_retries": 1, "maximum_actions": 20, "publication_retry_backoff_seconds": 1})
    _rewrite(manifest_path, manifest)
    assert profiles.render_profile_bundle(manifest_path)["status"] == "profile_bundle_ready"

    cfg = watchdog.validate_config({k: v for k, v in cfg.items() if k != "config_digest"})
    watchdog_path = tmp_path / "watchdog.json"; watchdog_path.write_text(json.dumps(cfg, sort_keys=True))
    source_root = tmp_path / "sources"; source_root.mkdir()
    work_root = tmp_path / "work-sources"; work_root.mkdir()
    signal = signal_plane.normalize_record({
        "source_kind": "run_tests", "finding_kind": "code", "severity": "high",
        "description": "Change allowed.txt deterministically", "subject_path": "allowed.txt",
        "source_artifact": "failure.json", "source_digest": "sha256:" + "1" * 64,
        "evidence_refs": ["operator:test"], "declared_validation_expectations": ["pytest_node:tests/fake.py::test_corrected"],
        "requested_authority_classes": policy["available_authority_classes"], "declared_constraints": ["bounded"],
        "estimated_file_count": 1, "estimated_changed_line_count": 10,
        "estimated_implementation_seconds": 10, "estimated_validation_seconds": 10,
    }, repo_root=repo)
    evaluation = signal_plane.evaluate_signal_plane([signal], repo_root=repo)
    (source_root / "signal.json").write_text(json.dumps(evaluation.to_dict(), sort_keys=True))
    collector_state = tmp_path / "collector-state"; collector_state.mkdir(mode=0o700)
    collector_cfg = {
        "schema_version": collector.CONFIG_SCHEMA, "repository_identity": "repo", "repository_root": str(repo),
        "base_sha": cfg["base_sha"], "activation_profile_bundle_manifest_path": str(manifest_path),
        "watchdog_configuration_path": str(watchdog_path), "collector_state_root": str(collector_state),
        "maintenance_candidate_inbox": str(roots["inbox"]),
        "governed_improvement_signal_source_roots": [str(source_root)], "normalized_work_item_source_roots": [str(work_root)],
        "allowed_source_schemas": [collector.GOVERNED_SIGNAL_SCHEMA], "allowed_source_kinds": ["governed_improvement_signal"],
        "maximum_source_records_per_scan": 2, "maximum_candidates_per_collection": 1, "maximum_input_bytes_per_record": 100000,
        "evaluation_time_required": True, "receipt_journal_path": str(collector_state / "receipts.jsonl"),
    }
    collector_path = tmp_path / "collector.json"; collector_path.write_text(json.dumps(collector_cfg, sort_keys=True))
    assert collector_main(["--config", str(collector_path), "--evaluation-time", NOW, "scan"]) == 0
    capsys.readouterr()
    assert collector_main(["--config", str(collector_path), "--evaluation-time", NOW, "collect-once"]) == 0
    collection = json.loads(capsys.readouterr().out)
    assert collection["candidates_written"] == 1 and len(list(roots["inbox"].glob("*.json"))) == 1

    os.environ["FAKE_CODEX_MODE"] = "corrective"
    assert watchdog_main(["--config", str(watchdog_path), "--evaluation-time", NOW, "run-bounded"]) == 0
    run = json.loads(capsys.readouterr().out)
    assert [tick["transition"] for tick in run["ticks"]] == ["select_candidate", "admit_candidate", "prepare_implementation", "start_implementation", "observe_process", "validate", "commit_enqueue", "publish", "close_task", "idle"]
    assert run["status"] == "idle"
    assert len(list((roots["state"] / "maintenance_leases").glob("*.json"))) == 1
    assert len(list((roots["state"] / "maintenance_agent_sessions").glob("*.json"))) == 1
    assert len(list((roots["state"] / "maintenance_validation_results").glob("*.json"))) == 2
    assert len(list((roots["state"] / "maintenance_commit_results").glob("*.json"))) == 1
    assert len(list((roots["state"] / "maintenance_publication_results").glob("*.json"))) == 1
    publication = next(t["effect_result"] for t in run["ticks"] if t["transition"] == "publish")
    assert all(publication[key] is False for key in ("force_push_used", "merge_performed", "hosted_checks_waited", "credential_bytes_inspected", "operator_message_relayed"))
    assert subprocess.run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=repo, text=True, capture_output=True, check=True).stdout.split()[0] != cfg["base_sha"]
