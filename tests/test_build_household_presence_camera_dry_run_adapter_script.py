import subprocess,sys,json
from pathlib import Path

FIX='tests/fixtures/household_presence_camera_dry_run_adapter'

def test_cli(tmp_path:Path):
 p=tmp_path/'policy.json'; o=tmp_path/'out.json'
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_dry_run_adapter.py','build-default','--output',str(p)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_dry_run_adapter.py','validate','--input',str(p)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_dry_run_adapter.py','run-fixture','--fixtures-dir',FIX,'--input','dry_run_fat_boi_wildlife_stream.json','--output',str(o)],check=False).returncode in {0,1}
 data=json.loads(o.read_text()); assert 'report' in data
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_dry_run_adapter.py','run-session','--input',str(Path(FIX)/'dry_run_mixed_household_exterior_stream.json'),'--summary'],check=False).returncode in {0,1}
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_dry_run_adapter.py','inspect-fixture','--fixtures-dir',FIX,'--input','dry_run_media_payload_rejected.json'],check=False).returncode==1
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_dry_run_adapter.py','summarize','--input',str(o)],check=False).returncode in {0,1}
