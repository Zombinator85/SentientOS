from __future__ import annotations
import json
from pathlib import Path
from sentientos.household_presence_camera_local_adapter_shell import build_default_policy,validate_policy,evaluate_local_adapter_shell
FIX=Path('tests/fixtures/household_presence_camera_local_adapter_shell')
def _f(n:str): return json.loads((FIX/n).read_text())

def test_policy_validates()->None: assert validate_policy(build_default_policy())['ok']

def test_success_and_review()->None:
 for n in ['valid_capture_disabled_usb_shell.json','valid_capture_disabled_integrated_shell.json','design_only_shell.json']:
  r=evaluate_local_adapter_shell(_f(n)).report; assert r.status in {'shell_ready_for_design','shell_ready_for_operator_review'} and r.capture_enabled is False and r.no_live_capture_performed is True
 assert evaluate_local_adapter_shell(_f('future_live_candidate_requires_review.json')).report.status=='shell_ready_for_operator_review'
 assert evaluate_local_adapter_shell(_f('network_camera_shell_operator_review.json')).report.status=='shell_ready_for_operator_review'
 assert evaluate_local_adapter_shell(_f('quest_visor_overlay_shell_review.json')).report.status=='shell_ready_for_operator_review'

def test_blocked()->None:
 m={'missing_stub_proof.json':'shell_blocked_missing_stub','missing_host_candidate.json':'shell_blocked_missing_host_candidate','missing_zone_config.json':'shell_blocked_missing_zone_config','missing_dry_run_proof.json':'shell_blocked_missing_dry_run_proof','missing_policy_chain.json':'shell_blocked_missing_policy_chain','invalid_capture_requested.json':'shell_blocked_live_capture_requested','invalid_live_hardware_requested.json':'shell_blocked_live_capture_requested','invalid_raw_media_requested.json':'shell_blocked_raw_media','invalid_speaker_requested.json':'shell_blocked_speaker_boundary','invalid_external_disclosure_requested.json':'shell_blocked_external_authority'}
 for k,v in m.items(): assert evaluate_local_adapter_shell(_f(k)).report.status==v

def test_deterministic()->None:
 p=_f('valid_capture_disabled_usb_shell.json'); a=evaluate_local_adapter_shell(p).report; b=evaluate_local_adapter_shell(p).report
 assert a.deterministic_digest==b.deterministic_digest and 'open_camera_now' in a.forbidden_next_steps and 'enable_live_capture' in a.forbidden_next_steps
