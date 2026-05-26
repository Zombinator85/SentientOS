from __future__ import annotations
import json
from pathlib import Path
from sentientos.household_presence_camera_live_adapter_stub import build_default_policy,validate_policy,evaluate_live_adapter_stub

FIX=Path('tests/fixtures/household_presence_camera_live_adapter_stub')
def _f(n:str): return json.loads((FIX/n).read_text())

def test_policy_validates()->None: assert validate_policy(build_default_policy())['ok']

def test_valid_and_review_and_boundaries()->None:
 r=evaluate_live_adapter_stub(_f('valid_stub_only_usb_camera.json')).report
 assert r.status in {'stub_ready_for_design','stub_ready_for_operator_review'} and r.live_hardware_enabled is False and r.no_live_capture_performed is True and 'open_camera_now' in r.forbidden_next_steps and 'bypass_policy_chain' in r.forbidden_next_steps
 assert evaluate_live_adapter_stub(_f('valid_stub_only_integrated_camera.json')).report.status in {'stub_ready_for_design','stub_ready_for_operator_review'}
 assert evaluate_live_adapter_stub(_f('network_camera_requires_review.json')).report.status=='stub_ready_for_operator_review'
 assert evaluate_live_adapter_stub(_f('quest_visor_overlay_only.json')).report.status=='stub_ready_for_operator_review'

def test_blocked_cases()->None:
 cases={
 'missing_operator_confirmation.json':'stub_blocked_missing_operator_confirmation',
 'invalid_live_hardware_allowed.json':'stub_blocked_live_hardware_requested',
 'invalid_raw_media_allowed.json':'stub_blocked_raw_media',
 'invalid_speaker_allowed.json':'stub_blocked_speaker_boundary',
 'invalid_external_disclosure_allowed.json':'stub_blocked_external_authority',
 'missing_host_candidate.json':'stub_blocked_missing_host_candidate',
 'missing_zone_config.json':'stub_blocked_missing_zone_config',
 'missing_dry_run_proof.json':'stub_blocked_missing_dry_run_proof',
 'failed_dry_run_proof.json':'stub_blocked_missing_dry_run_proof',
 'stale_dry_run_proof.json':'stub_blocked_missing_dry_run_proof',
 'microphone_only_candidate_blocked.json':'stub_failed',
 'speaker_talkback_candidate_blocked.json':'stub_failed',
 }
 for name,expected in cases.items(): assert evaluate_live_adapter_stub(_f(name)).report.status==expected

def test_deterministic_digest()->None:
 p=_f('valid_stub_only_usb_camera.json'); assert evaluate_live_adapter_stub(p).report.deterministic_digest==evaluate_live_adapter_stub(p).report.deterministic_digest
