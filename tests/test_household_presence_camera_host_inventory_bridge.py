from sentientos.household_presence_camera_host_inventory_bridge import build_default_policy, validate_policy, evaluate_inventory, load_inventory_fixture
FIX='tests/fixtures/household_presence_camera_host_inventory_bridge'

def test_policy_valid(): assert validate_policy(build_default_policy())["ok"]
def _r(name): return evaluate_inventory(load_inventory_fixture(f"{FIX}/{name}")).report

def test_usb_candidate_not_live():
 r=_r('usb_camera_inventory.json'); c=r.candidates[0]; assert c.readiness_recommendation in {'candidate_for_dry_run_only','candidate_for_operator_review'}; assert c.live_hardware_allowed is False

def test_integrated_candidate_not_live(): assert _r('integrated_camera_inventory.json').candidates[0].live_hardware_allowed is False
def test_microphone_blocked(): assert len(_r('microphone_only_inventory.json').candidates)==0
def test_speaker_blocked(): assert len(_r('speaker_talkback_inventory.json').candidates)==0
def test_virtual_operator_review(): assert _r('virtual_camera_inventory.json').candidates[0].readiness_recommendation=='candidate_for_operator_review'
def test_network_operator_review(): assert _r('network_camera_metadata_inventory.json').candidates[0].readiness_recommendation=='candidate_for_operator_review'
def test_quest_metadata_only(): assert 'future_overlay_metadata_only' in _r('quest_visor_inventory.json').candidates[0].notes
def test_unknown_operator_review(): assert _r('unknown_video_device_inventory.json').candidates[0].readiness_recommendation=='candidate_for_operator_review'
def test_missing_policy_chain_blocks(): assert _r('missing_policy_chain_inventory.json').candidates[0].readiness_recommendation=='blocked_missing_policy_chain'
def test_deterministic_digest():
 p=load_inventory_fixture(f"{FIX}/mixed_devices_inventory.json")
 assert evaluate_inventory(p).report.deterministic_digest==evaluate_inventory(p).report.deterministic_digest
