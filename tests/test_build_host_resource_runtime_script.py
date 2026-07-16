from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
import subprocess, sys, os, json


def test_host_resource_runtime_cli_plan_and_collect(tmp_path):
    env = {**os.environ, "SENTIENTOS_RUNTIME_STATE_ROOT": str(tmp_path), "PYTHONPATH": "."}
    out = subprocess.check_output([sys.executable, "scripts/build_host_resource_runtime.py", "plan"], text=True, env=env)
    assert "host_resource_observation" in out or "collectors" in out
    val = subprocess.check_output([sys.executable, "scripts/build_host_resource_runtime.py", "validate-plan"], text=True, env=env)
    assert json.loads(val)["ok"] is True
    md = subprocess.check_output([sys.executable, "scripts/build_host_resource_runtime.py", "render-markdown", "--output-root", str(tmp_path), "--correlation-id", "cli-test"], text=True, env=env)
    assert "Effects: `none`" in md
