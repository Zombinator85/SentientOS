from pathlib import Path
import json
from sentientos.household_presence_camera_policy_chain import build_default_policy, evaluate_policy_chain, validate_policy

FIX=Path('tests/fixtures/household_presence_camera_policy_chain')

def load(n): return json.loads((FIX/n).read_text())

def test_default_policy_validates(): assert validate_policy(build_default_policy())['ok']

def test_routes():
    assert evaluate_policy_chain(load('chain_fat_boi_wildlife_allowed.json')).decision.route=='wildlife_ledger_candidate'
    assert evaluate_policy_chain(load('chain_deadzone_blocks.json')).decision.route=='blocked_by_deadzone'
    assert evaluate_policy_chain(load('chain_sensitive_missing_redaction_blocks.json')).decision.route=='blocked_by_missing_redaction'
    assert evaluate_policy_chain(load('chain_sensitive_redacted_security_allowed.json')).decision.route in {'redacted_ambient_journal','security_event_metadata'}
    assert evaluate_policy_chain(load('chain_speaker_request_blocked.json')).decision.route=='blocked_by_speaker_boundary'
    assert evaluate_policy_chain(load('chain_external_authority_blocked.json')).decision.route=='blocked_by_external_authority_boundary'

def test_digest_deterministic_and_stages():
    r1=evaluate_policy_chain(load('chain_exterior_person_security_only.json'))
    r2=evaluate_policy_chain(load('chain_exterior_person_security_only.json'))
    assert r1.digest==r2.digest
    names=[s.name for s in r1.report.stages]
    assert names[:4]==['input_loaded','event_bridge_normalized','zone_resolved','redaction_contract_evaluated']
