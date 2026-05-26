from __future__ import annotations
import subprocess,sys
from pathlib import Path

def test_script_commands(tmp_path:Path)->None:
 p=tmp_path/'d.json'; o=tmp_path/'o.json'
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_stub.py','build-default','--output',str(p)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_stub.py','validate','--input',str(p)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_stub.py','evaluate','--fixtures-dir','tests/fixtures/household_presence_camera_live_adapter_stub','--output',str(o)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_stub.py','summarize','--input',str(o)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_live_adapter_stub.py','inspect-fixture','--input','missing_operator_confirmation.json'],check=False).returncode==1
