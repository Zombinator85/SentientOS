from pathlib import Path
from sentientos.household_presence_camera_disabled_capture_adapter import build_default_policy,validate_policy,evaluate_disabled_capture,load_fixture
FIX=Path('tests/fixtures/household_presence_camera_disabled_capture_adapter')

def test_default_policy_validates(): assert validate_policy(build_default_policy())["ok"]
def _s(n:str)->str: return evaluate_disabled_capture(load_fixture(str(FIX/n))).report.status

def test_statuses_and_blocks():
    assert _s('design_only_disabled_capture_ready.json')=='disabled_capture_ready_for_design'
    assert _s('dry_run_only_disabled_capture_ready.json')=='disabled_capture_ready_for_dry_run'
    assert _s('boundary_operator_review.json')=='disabled_capture_operator_review_required'
    assert _s('future_live_candidate_review_only.json')=='disabled_capture_operator_review_required'
    for n in ['capture_attempt_blocked.json','capture_requested_blocked.json']: assert _s(n)=='disabled_capture_blocked_capture_requested'
    assert _s('live_hardware_requested_blocked.json')=='disabled_capture_blocked_live_hardware_requested'
    for n in ['raw_media_requested_blocked.json','raw_media_payload_present_blocked.json','base64_media_present_blocked.json']: assert _s(n)=='disabled_capture_blocked_raw_media_requested'
    assert _s('speaker_requested_blocked.json')=='disabled_capture_blocked_speaker_boundary'
    assert _s('external_disclosure_requested_blocked.json')=='disabled_capture_blocked_external_authority'
    assert _s('missing_shell_proof_blocked.json')=='disabled_capture_blocked_missing_shell_proof'
    assert _s('missing_stub_proof_blocked.json')=='disabled_capture_blocked_missing_stub_proof'
    assert _s('missing_policy_chain_blocked.json')=='disabled_capture_blocked_missing_policy_chain'
    assert _s('missing_zone_config_blocked.json')=='disabled_capture_blocked_missing_zone_config'

def test_success_binding_and_digest_deterministic():
    r=evaluate_disabled_capture(load_fixture(str(FIX/'dry_run_only_disabled_capture_ready.json'))).report
    assert r.binding.capture_enabled is False and r.binding.capture_available is False and r.binding.no_live_capture_performed is True
    assert 'attempt_capture' in r.forbidden_next_steps and 'enable_live_capture' in r.forbidden_next_steps
    d1=r.deterministic_digest; d2=evaluate_disabled_capture(load_fixture(str(FIX/'dry_run_only_disabled_capture_ready.json'))).report.deterministic_digest
    assert d1==d2 and len(d1)==64
