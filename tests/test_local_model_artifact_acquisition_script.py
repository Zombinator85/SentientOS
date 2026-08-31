from __future__ import annotations
import json
from pathlib import Path
import pytest
from scripts import local_model_artifact_acquisition as cli

pytestmark = pytest.mark.no_legacy_skip

def _inputs(tmp_path: Path):
    paths=[]
    for name in ("selection","runtime","backend","catalog"):
        path=tmp_path/f"{name}.json"; path.write_text("{}",encoding="utf-8");paths.append(path)
    return paths

def test_cli_inspection_has_no_execution_authorization(tmp_path: Path,monkeypatch,capsys):
    paths=_inputs(tmp_path); plan={"acquisition_plan_digest":"a"*64}
    monkeypatch.setattr(cli,"compose_acquisition_plan",lambda *a:plan)
    seen={}
    def acquire(value,**kwargs): seen.update(kwargs);return {"status":"inspection_ready"}
    monkeypatch.setattr(cli,"acquire_model_artifact",acquire)
    args=["--selection-plan",str(paths[0]),"--runtime-provisioning-plan",str(paths[1]),
        "--backend-verification-receipt",str(paths[2]),"--local-model-catalog",str(paths[3]),
        "--escrow-root",str(tmp_path/"escrow")]
    assert cli.main(args)==0 and seen["execute"] is False and seen["authorization"] is None
    assert json.loads(capsys.readouterr().out)["result"]["status"]=="inspection_ready"

def test_cli_execute_requires_exact_plan_digest(tmp_path: Path,monkeypatch,capsys):
    paths=_inputs(tmp_path); plan={"acquisition_plan_digest":"a"*64}
    monkeypatch.setattr(cli,"compose_acquisition_plan",lambda *a:plan)
    args=["--selection-plan",str(paths[0]),"--runtime-provisioning-plan",str(paths[1]),
        "--backend-verification-receipt",str(paths[2]),"--local-model-catalog",str(paths[3]),"--execute",
        "--confirm-plan-digest","b"*64]
    assert cli.main(args)==2
    assert json.loads(capsys.readouterr().out)["reason_code"]=="confirmed_plan_digest_mismatch"
