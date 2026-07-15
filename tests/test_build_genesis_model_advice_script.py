from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from sentientos.genesis_model_advice import SCHEMA_VERSION

def test_cli_validate_advice_output(tmp_path: Path) -> None:
    p=tmp_path/'advice.json'
    p.write_text(json.dumps({'schema_version':SCHEMA_VERSION,'objective_refinement':'Honor gap','proposed_directives':['preserve_lineage'],'testing_requirements':['acknowledge_capability'],'rationale':'Advisory only.','capability_interpretation':'Bounded gap.'}),encoding='utf-8')
    res=subprocess.run([sys.executable,'scripts/build_genesis_model_advice.py','validate-advice-output',str(p)],cwd=Path.cwd(),text=True,capture_output=True)
    assert res.returncode==0
    assert '"valid": true' in res.stdout
