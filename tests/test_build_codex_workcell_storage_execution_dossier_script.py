from __future__ import annotations

import json
import pytest
import subprocess
import sys
from pathlib import Path

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_execution_dossier import INPUT_SPECS

SCRIPT="scripts/build_codex_workcell_storage_execution_dossier.py"

def _write_reports(tmp_path: Path):
    args=[]
    for input_id,_,_ in INPUT_SPECS:
        data={"non_authority_posture":{"a":True}}
        if input_id=="storage_policy_verifier_json": data["verification_status"]="storage_policy_verified"
        if input_id=="storage_transaction_plan_verifier_json": data["verification_status"]="storage_transaction_plan_verified"
        p=tmp_path/f"{input_id}.json"; p.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        args += ["--"+input_id.replace("_","-"), str(p)]
    return args


def test_cli_writes_json_markdown_and_summary(tmp_path: Path):
    out=tmp_path/"out.json"; md=tmp_path/"out.md"
    cmd=[sys.executable,SCRIPT,"--output",str(out),"--markdown-output",str(md),"--summary"]+_write_reports(tmp_path)
    res=subprocess.run(cmd, check=True, text=True, capture_output=True)
    assert "future_storage_design_dossier_complete" in res.stdout
    first=out.read_text(); second=subprocess.run(cmd, check=True, text=True, capture_output=True)
    assert second.returncode==0 and out.read_text()==first
    assert md.read_text()==md.read_text()
    data=json.loads(first)
    assert data["active_execution_gap_summary"]["active_storage_allowed_now"] is False


def test_cli_invalid_missing_and_non_object_exit_2(tmp_path: Path):
    out=tmp_path/"out.json"
    bad=tmp_path/"bad.json"; bad.write_text("{", encoding="utf-8")
    res=subprocess.run([sys.executable,SCRIPT,"--output",str(out),"--memory-contract-json",str(bad)], text=True, capture_output=True)
    assert res.returncode==2 and "invalid_json" in res.stderr
    res=subprocess.run([sys.executable,SCRIPT,"--output",str(out),"--memory-contract-json",str(tmp_path/"missing.json")], text=True, capture_output=True)
    assert res.returncode==2 and "missing_json" in res.stderr
    arr=tmp_path/"arr.json"; arr.write_text("[]", encoding="utf-8")
    res=subprocess.run([sys.executable,SCRIPT,"--output",str(out),"--memory-contract-json",str(arr)], text=True, capture_output=True)
    assert res.returncode==2 and "json_not_object" in res.stderr


def test_cli_omitted_inputs_incomplete(tmp_path: Path):
    out=tmp_path/"out.json"
    subprocess.run([sys.executable,SCRIPT,"--output",str(out),"--summary"], check=True, text=True, capture_output=True)
    data=json.loads(out.read_text())
    assert data["storage_execution_status"]=="future_storage_design_dossier_incomplete"
    assert data["writes_performed"] is False and data["archives_performed"] is False
    assert data["not_daemon_action"] is True and data["not_task_creator"] is True
