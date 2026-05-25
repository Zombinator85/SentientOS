import subprocess,sys
from pathlib import Path

def test_cli(tmp_path: Path):
    p=tmp_path/'p.json'; o=tmp_path/'o.json'
    subprocess.run([sys.executable,'scripts/build_household_presence_camera_policy_chain.py','build-default','--output',str(p)],check=True)
    assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_policy_chain.py','validate','--input',str(p)],check=False).returncode==0
    assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_policy_chain.py','run-fixture','--name','chain_fat_boi_wildlife_allowed.json','--output',str(o)],check=False).returncode==0
    assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_policy_chain.py','summarize','--input','tests/fixtures/household_presence_camera_policy_chain/chain_deadzone_blocks.json'],check=False).returncode!=0
