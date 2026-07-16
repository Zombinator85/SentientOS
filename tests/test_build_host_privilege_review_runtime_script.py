from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import pytest
pytestmark = pytest.mark.no_legacy_skip

def test_cli_plan_and_projection_commands(tmp_path):
    env = {**os.environ, "PYTHONPATH": "."}
    plan = subprocess.run([sys.executable, "scripts/build_host_privilege_review_runtime.py", "plan"], check=True, text=True, capture_output=True, env=env)
    data = json.loads(plan.stdout)
    assert data["metadata_only"] is True and data["effect_authority"] is False
    fixture = tmp_path / "evaluation.json"
    fixture.write_text(json.dumps({"evaluation_id":"e", "chain_id":"c", "items":[], "summary":{"host_mutation_performed": False}, "no_effect_authority": True}), encoding="utf-8")
    val = subprocess.run([sys.executable, "scripts/build_host_privilege_review_runtime.py", "validate-evaluation", "--input", str(fixture)], check=True, text=True, capture_output=True, env=env)
    assert json.loads(val.stdout)["valid"] is True
    md = subprocess.run([sys.executable, "scripts/build_host_privilege_review_runtime.py", "render-markdown", "--input", str(fixture)], check=True, text=True, capture_output=True, env=env)
    assert "rehearsal is not execution" in md.stdout
