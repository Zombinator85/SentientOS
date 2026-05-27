import json,subprocess,sys
from pathlib import Path

SCRIPT='scripts/build_household_presence_camera_capture_authorization.py'
FIX='tests/fixtures/household_presence_camera_capture_authorization/valid_design_only_authorization.json'

def test_cli_build_default_and_evaluate(tmp_path: Path):
    r=subprocess.run([sys.executable,SCRIPT,'build-default'],check=True,capture_output=True,text=True)
    assert 'schema_version' in r.stdout
    out=tmp_path/'o.json'
    ok=subprocess.run([sys.executable,SCRIPT,'evaluate','--input',FIX,'--output',str(out)],check=True,capture_output=True,text=True)
    payload=json.loads(out.read_text())
    assert payload['capture_enabled'] is False
