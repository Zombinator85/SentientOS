from __future__ import annotations
import json
from pathlib import Path
from sentientos.household_presence_camera_capture_denial_ledger import build_default_policy, validate_policy, evaluate_capture_denial_ledger
FIX=Path('tests/fixtures/household_presence_camera_capture_denial_ledger')

def _f(name:str): return json.loads((FIX/name).read_text())

def test_policy_valid(): assert validate_policy(build_default_policy())['ok']

def test_missing_operator_maps_action():
    r=evaluate_capture_denial_ledger(_f('missing_operator_grant_denial.json'))
    assert r.ledger.records[0].safe_next_action=='renew_operator_grant'
    assert not r.ledger.records[0].media_present

def test_media_payload_blocked():
    r=evaluate_capture_denial_ledger(_f('raw_media_payload_blocked.json'))
    assert r.status=='capture_denial_ledger_blocked_media_payload'

def test_external_blocked():
    r=evaluate_capture_denial_ledger(_f('external_authority_denial.json'))
    assert r.status=='capture_denial_ledger_blocked_external_authority'

def test_mixed_deterministic():
    p=_f('mixed_denial_ledger.json'); r1=evaluate_capture_denial_ledger(p); r2=evaluate_capture_denial_ledger(p)
    assert r1.ledger.digest==r2.ledger.digest

def test_non_denial_warning():
    r=evaluate_capture_denial_ledger(_f('non_denial_success_rejected.json'))
    assert r.status=='capture_denial_ledger_valid_with_warnings'
