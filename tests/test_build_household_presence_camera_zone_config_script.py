import subprocess,sys,json

def run(*a):
    return subprocess.run([sys.executable,'scripts/build_household_presence_camera_zone_config.py',*a],capture_output=True,text=True)

def test_cli_build_default_validate_and_inspect():
    assert run('build-default','--summary').returncode==0
    assert run('inspect-fixture','--input','invalid_external_disclosure_config.json').returncode==1
