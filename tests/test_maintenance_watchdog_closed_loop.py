import json
import os
import subprocess

import pytest

from scripts.maintenance_loop_watchdog import main
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos.maintenance_validation_controller import ValidationPolicy
from tests.maintenance_watchdog_implementation_fixtures import NOW, setup

pytestmark = pytest.mark.no_legacy_skip


def test_production_cli_process_real_fake_cycle_reaches_idle(tmp_path, capsys):
    cfg, roots, repo = setup(tmp_path, closed_loop=True,
        validation_expectations=["pytest_node:tests/fake.py::test_corrected"])
    validator = tmp_path / "validator.py"
    validator.write_text("#!/usr/bin/env python3\nfrom pathlib import Path\nraise SystemExit(0 if Path('allowed.txt').read_text() == 'corrected\\n' else 1)\n")
    validator.chmod(0o755)
    cfg = dict(cfg)
    cfg["validation_policy"] = ValidationPolicy("closed-loop", "repo",
        python_executable=str(validator), external_scratch_root=str(roots["scratch"]),
        per_command_default_ceiling_seconds=2, maximum_controller_cycles=2,
        maximum_corrective_retries=1).to_dict()
    cfg["maximum_actions"] = 20
    cfg = watchdog.validate_config({k: v for k, v in cfg.items() if k != "config_digest"})
    config_path = tmp_path / "watchdog.json"
    config_path.write_text(json.dumps(cfg, sort_keys=True))
    os.environ["FAKE_CODEX_MODE"] = "corrective"

    assert main(["--config", str(config_path), "--evaluation-time", NOW, "run-bounded"]) == 0
    run = json.loads(capsys.readouterr().out)
    assert [tick["transition"] for tick in run["ticks"]] == [
        "select_candidate", "admit_candidate", "prepare_implementation",
        "start_implementation", "observe_process", "validate", "commit_enqueue",
        "publish", "close_task", "idle"]
    assert run["status"] == "idle"
    state = roots["state"]
    assert len(list((state / "maintenance_leases").glob("*.json"))) == 1
    assert len(list((state / "maintenance_agent_sessions").glob("*.json"))) == 1
    assert len(list((state / "maintenance_validation_results").glob("*.json"))) == 2
    assert len(list((state / "maintenance_commit_results").glob("*.json"))) == 1
    assert len(list((state / "maintenance_publication_results").glob("*.json"))) == 1
    invocations = list((state / "maintenance_codex_invocations").glob("*.json"))
    assert len(invocations) == 2
    assert {json.loads(path.read_text())["session_id"] for path in invocations} == {
        json.loads(next((state / "maintenance_agent_sessions").glob("*.json")).read_text())["session_id"]}
    assert len(list((state / "maintenance_local_codex_invocations").glob("*.json"))) == 0
    remote = subprocess.run(["git", "ls-remote", "origin", "refs/heads/main"],
        cwd=repo, text=True, capture_output=True, check=True).stdout.split()[0]
    assert remote != cfg["base_sha"]
    publication = next(t["effect_result"] for t in run["ticks"] if t["transition"] == "publish")
    assert publication["force_push_used"] is False
    assert publication["merge_performed"] is False
    assert publication["hosted_checks_waited"] is False
    assert publication["credential_bytes_inspected"] is False
    assert publication["operator_message_relayed"] is False
