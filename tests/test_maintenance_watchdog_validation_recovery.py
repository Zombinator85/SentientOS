import pytest
pytestmark = pytest.mark.no_legacy_skip
import os
import json

from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_validation_controller as controller
from sentientos import maintenance_task_journal as journal
from sentientos.maintenance_validation_controller import ValidationPolicy
from tests.maintenance_watchdog_implementation_fixtures import NOW, setup


def test_correctable_failure_resumes_same_thread_remeasures_and_revalidates(tmp_path):
    cfg, roots, _ = setup(tmp_path, validation_expectations=["pytest_node:tests/fake.py::test_corrected"])
    validator = tmp_path / "validator.py"
    validator.write_text("#!/usr/bin/env python3\nfrom pathlib import Path\nraise SystemExit(0 if Path('allowed.txt').read_text() == 'corrected\\n' else 1)\n")
    validator.chmod(0o755)
    cfg = dict(cfg)
    cfg["validation_policy"] = ValidationPolicy(
        "watchdog", "repo", python_executable=str(validator),
        external_scratch_root=str(roots["scratch"]), per_command_default_ceiling_seconds=2,
        maximum_controller_cycles=2, maximum_corrective_retries=1).to_dict()
    cfg = watchdog.validate_config({k: v for k, v in cfg.items() if k != "config_digest"})
    os.environ["FAKE_CODEX_MODE"] = "corrective"
    for _ in range(5): watchdog.tick(cfg, evaluation_time=NOW)
    result = watchdog.tick(cfg, evaluation_time=NOW)["effect_result"]
    assert result["status"] == "validation_ready_for_commit"
    assert result["validation_plan"]["validation_cycle_ordinal"] == 2
    assert result["validation_plan"]["codex_thread_id"] == "thread-ok"
    assert len(list((roots["state"] / "maintenance_validation_results").glob("*.json"))) == 2
    assert next((roots["workspace"]).rglob("allowed.txt")).read_text() == "corrected\n"


def test_noncorrrectable_timeout_blocks_without_commit(tmp_path):
    cfg, roots, _ = setup(tmp_path, validation_expectations=["pytest_node:tests/fake.py::test_timeout"])
    validator = tmp_path / "validator.py"
    validator.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
    validator.chmod(0o755)
    cfg = dict(cfg)
    cfg["validation_policy"] = ValidationPolicy("watchdog", "repo",
        python_executable=str(validator), external_scratch_root=str(roots["scratch"]),
        per_command_default_ceiling_seconds=.05).to_dict()
    cfg = watchdog.validate_config({k: v for k, v in cfg.items() if k != "config_digest"})
    os.environ["FAKE_CODEX_MODE"] = "success"
    for _ in range(5): watchdog.tick(cfg, evaluation_time=NOW)
    result = watchdog.tick(cfg, evaluation_time=NOW)["effect_result"]
    assert result["status"] == "validation_timed_out"
    assert not (roots["state"] / "maintenance_commit_results").exists()


def test_partial_validation_custody_routes_through_controller_recovery(tmp_path, monkeypatch):
    cfg, roots, repo = setup(tmp_path)
    cfg = dict(cfg)
    policy = ValidationPolicy("watchdog", "repo", external_scratch_root=str(roots["scratch"]),
        per_command_default_ceiling_seconds=2)
    cfg["validation_policy"] = policy.to_dict()
    cfg = watchdog.validate_config({k: v for k, v in cfg.items() if k != "config_digest"})
    os.environ["FAKE_CODEX_MODE"] = "success"
    for _ in range(5): watchdog.tick(cfg, evaluation_time=NOW)
    scanned = watchdog.scan(cfg, evaluation_time=NOW)
    snap = scanned["observations"]["active_tasks"][0]
    task = snap["task_id"]
    lease = watchdog._lease_for(snap, cfg)
    impl = watchdog._owned(scanned, controller.foreman.RESULT_SCHEMA, task)[0]
    session = watchdog._owned(scanned, watchdog.implementation_agent.SESSION_SCHEMA, task)[0]
    impl.update(attempt_id=session["attempt_id"], attempt_ordinal=1, corrective_retry_ordinal=0)
    worktree = watchdog._owned(scanned, controller.foreman.WORKTREE_SCHEMA, task)[0]
    manifest = watchdog._owned(scanned, controller.foreman.CHANGE_SCHEMA, task)[0]
    plan = controller.build_validation_plan(policy=policy, lease=lease,
        implementation_result=impl, worktree=worktree, change_manifest=manifest)
    path = roots["state"] / "maintenance_validation_plans" / f"{plan['validation_ref_id']}.json"
    path.parent.mkdir(); path.write_text(json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n")
    payload = {"validation_ref_id": plan["validation_ref_id"], "attempt_id": plan["attempt_id"],
        "session_id": plan["implementation_session_id"], "plan_digest": plan["plan_digest"],
        "change_manifest_digest": plan["change_manifest_digest"],
        "worktree_descriptor_digest": plan["worktree_descriptor_digest"]}
    journal.append_event(roots["state"], "validation_started", task_id=task, payload=payload,
        repo_root=repo, recorded_at=NOW)
    seen = {}
    def fake(**kwargs):
        seen.update(kwargs)
        return {"status": "validation_interrupted"}
    monkeypatch.setattr(controller, "advance_validation_controller", fake)
    tick = watchdog.tick(cfg, evaluation_time=NOW)
    assert tick["transition"] == "recover_validation"
    assert seen["recovery_plan"]["plan_digest"] == plan["plan_digest"]
