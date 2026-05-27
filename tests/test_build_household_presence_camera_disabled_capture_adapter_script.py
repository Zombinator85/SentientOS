import subprocess,sys
from pathlib import Path
FIX='tests/fixtures/household_presence_camera_disabled_capture_adapter'

def test_cli_commands(tmp_path: Path):
 p=tmp_path/'p.json'; o=tmp_path/'o.json'
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_disabled_capture_adapter.py','build-default','--output',str(p)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_disabled_capture_adapter.py','validate','--input',str(p)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_disabled_capture_adapter.py','evaluate','--fixtures-dir',FIX,'--fixture','dry_run_only_disabled_capture_ready.json','--output',str(o)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_disabled_capture_adapter.py','evaluate','--fixtures-dir',FIX,'--fixture','capture_requested_blocked.json'],check=False).returncode==1
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_disabled_capture_adapter.py','inspect-fixture','--fixtures-dir',FIX,'--input','missing_stub_proof_blocked.json'],check=False).returncode==1
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_disabled_capture_adapter.py','summarize','--input',str(o)],check=False).returncode==0
