from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import pytest
pytestmark = pytest.mark.no_legacy_skip

def test_plan_and_validate_plan(tmp_path):
    plan = tmp_path / "plan.json"
    r = subprocess.run([sys.executable, "scripts/build_host_execution_readiness_runtime.py", "plan", "--output", str(plan)], text=True, capture_output=True)
    assert r.returncode == 0 and plan.exists()
    r = subprocess.run([sys.executable, "scripts/build_host_execution_readiness_runtime.py", "validate-plan", str(plan)], text=True, capture_output=True)
    assert r.returncode == 0
    assert json.loads(r.stdout)["status"] == "valid"

def test_evaluate_requires_explicit_typed_source(tmp_path):
    src = tmp_path / "src.json"; src.write_text('{"evaluation_id":"ev"}', encoding="utf-8")
    r = subprocess.run([sys.executable, "scripts/build_host_execution_readiness_runtime.py", "evaluate", "--privilege-review-evaluation", str(src), "--output-root", str(tmp_path)], text=True, capture_output=True)
    assert r.returncode == 2
    assert json.loads(r.stdout)["authorization_granted"] is False

def test_render_and_diff(tmp_path):
    ev = tmp_path / "ev.json"; ev.write_text(json.dumps({"evaluation_id":"e1","items":[{"item_id":"i1"}],"summary":{"status":"ok"}}), encoding="utf-8")
    assert subprocess.run([sys.executable, "scripts/build_host_execution_readiness_runtime.py", "list-items", str(ev)], capture_output=True).returncode == 0
    assert subprocess.run([sys.executable, "scripts/build_host_execution_readiness_runtime.py", "render-markdown", str(ev)], capture_output=True).returncode == 0
    assert subprocess.run([sys.executable, "scripts/build_host_execution_readiness_runtime.py", "diff", str(ev), str(ev)], capture_output=True).returncode == 0
