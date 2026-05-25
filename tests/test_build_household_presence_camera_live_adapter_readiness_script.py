import subprocess,sys,json
from pathlib import Path

def test_cli(tmp_path:Path):
 p=tmp_path/'policy.json';o=tmp_path/'out.json'
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_readiness.py','build-default','--output',str(p)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_readiness.py','validate','--input',str(p)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_readiness.py','evaluate','--workspace-root','.','--fixtures-dir','tests/fixtures/household_presence_camera_live_adapter_readiness','--output',str(o)],check=False).returncode in {0,1}
 data=json.loads(o.read_text()); assert 'report' in data
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_readiness.py','summarize','--input',str(o)],check=False).returncode in {0,1}
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_readiness.py','inspect-fixture','--input','live_runtime_risk_present.json'],check=False).returncode==1
