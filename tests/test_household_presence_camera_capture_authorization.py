from pathlib import Path
import json
from sentientos.household_presence_camera_capture_authorization import build_default_policy,validate_policy,evaluate_capture_authorization

FIX=Path('tests/fixtures/household_presence_camera_capture_authorization')

def _f(n): return json.loads((FIX/n).read_text())

def test_default_policy_validates(): assert validate_policy(build_default_policy())["ok"]

def test_valid_design_and_dry_run_do_not_enable_capture():
    for n in ('valid_design_only_authorization.json','valid_dry_run_only_authorization.json'):
        r=evaluate_capture_authorization(_f(n)).to_dict(); assert r['capture_enabled'] is False and r['authorization_enables_live_capture'] is False and r['no_live_capture_performed'] is True

def test_blocked_fixtures_block():
    for n in FIX.glob('*blocked.json'):
        assert evaluate_capture_authorization(_f(n)).status.startswith('capture_authorization_blocked')

def test_forbidden_next_steps_present():
    r=evaluate_capture_authorization(_f('valid_design_only_authorization.json')).to_dict()
    for key in ('attempt_capture','enable_live_capture','bypass_disabled_capture_boundary'): assert key in r['forbidden_next_steps']
