from __future__ import annotations
import json
from pathlib import Path
from sentientos.household_presence_camera_capture_review_packet import build_default_policy,evaluate_capture_review_packet
FIX=Path('tests/fixtures/household_presence_camera_capture_review_packet')

def _j(n:str): return json.loads((FIX/n).read_text())

def test_default_policy_validates(): assert build_default_policy().schema_version.endswith('.v1')

def test_valid_design_review_packet_operator_only():
    r=evaluate_capture_review_packet(_j('valid_design_review_packet.json')); assert r.status=='capture_review_packet_ready_for_operator_review'; assert not r.packet.capture_enabled and r.packet.no_live_capture_performed

def test_valid_dry_run_review_packet(): assert evaluate_capture_review_packet(_j('valid_dry_run_review_packet.json')).status=='capture_review_packet_ready_for_dry_run_only'

def test_future_live_review_operator_only(): assert evaluate_capture_review_packet(_j('future_live_review_operator_only.json')).status=='capture_review_packet_ready_for_operator_review'

def test_blockers():
    m={'missing_authorization_blocked.json':'capture_review_packet_blocked_missing_authorization','missing_denial_ledger_blocked.json':'capture_review_packet_blocked_missing_denial_ledger','missing_disabled_capture_proof_blocked.json':'capture_review_packet_blocked_missing_disabled_capture_proof','missing_shell_proof_blocked.json':'capture_review_packet_blocked_missing_shell_proof','missing_stub_proof_blocked.json':'capture_review_packet_blocked_missing_stub_proof','missing_host_candidate_blocked.json':'capture_review_packet_blocked_missing_host_candidate','missing_zone_config_blocked.json':'capture_review_packet_blocked_missing_zone_config','missing_dry_run_proof_blocked.json':'capture_review_packet_blocked_missing_dry_run_proof','missing_policy_chain_blocked.json':'capture_review_packet_blocked_missing_policy_chain','unresolved_denials_blocked.json':'capture_review_packet_blocked_unresolved_denials','scope_mismatch_blocked.json':'capture_review_packet_blocked_scope_mismatch','stale_proof_blocked.json':'capture_review_packet_blocked_stale_proof','media_payload_blocked.json':'capture_review_packet_blocked_media_payload','base64_payload_blocked.json':'capture_review_packet_blocked_media_payload','speaker_boundary_blocked.json':'capture_review_packet_blocked_speaker_boundary','external_authority_blocked.json':'capture_review_packet_blocked_external_authority'}
    for f,s in m.items(): assert evaluate_capture_review_packet(_j(f)).status==s

def test_forbidden_next_steps_and_deterministic_digest():
    a=evaluate_capture_review_packet(_j('valid_design_review_packet.json')); b=evaluate_capture_review_packet(_j('valid_design_review_packet.json'))
    assert a.packet.digest==b.packet.digest and 'attempt_capture' in a.packet.forbidden_next_steps and 'bypass_denial_ledger' in a.packet.forbidden_next_steps
