import subprocess,sys
from pathlib import Path
FIX='tests/fixtures/household_presence_camera_host_inventory_bridge'

def test_cli_commands(tmp_path: Path):
 o=tmp_path/'out.json'; d=tmp_path/'default.json'
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_host_inventory_bridge.py','build-default','--output',str(d)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_host_inventory_bridge.py','evaluate','--input',f'{FIX}/mixed_devices_inventory.json','--output',str(o)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_host_inventory_bridge.py','validate','--input',str(o)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_host_inventory_bridge.py','summarize','--input',str(o)],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_host_inventory_bridge.py','inspect-fixture','--fixtures-dir',FIX,'--input','mixed_devices_inventory.json'],check=False).returncode==0
 assert subprocess.run([sys.executable,'scripts/build_household_presence_camera_host_inventory_bridge.py','inspect-repo','--workspace-root','.'],check=False).returncode==0
