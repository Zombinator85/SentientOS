from sentientos.household_presence_camera_dry_run_adapter import build_default_policy, validate_policy, evaluate_dry_run_session, load_session_fixture

FIX='tests/fixtures/household_presence_camera_dry_run_adapter'

def test_default_policy_validates(): assert validate_policy(build_default_policy())["ok"]
def test_missing_operator_confirmation_blocks(): assert evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_missing_operator_confirmation.json")).report.status=="dry_run_operator_confirmation_required"
def test_live_hardware_confirmation_blocks(): assert evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_invalid_live_hardware_confirmation.json")).report.status=="dry_run_operator_confirmation_required"
def test_fat_boi_wildlife_routes(): assert evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_fat_boi_wildlife_stream.json")).report.route_counts.get("wildlife_ledger_candidate",0)>=0
def test_deadzone_stream_blocks(): assert evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_deadzone_block_stream.json")).report.status in {"dry_run_blocked","dry_run_ready_with_warnings","dry_run_ready"}
def test_speaker_and_external_blocks():
 assert "blocked_by_speaker_boundary" in evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_speaker_request_block_stream.json")).report.route_counts
 assert "blocked_by_external_authority_boundary" in evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_external_authority_block_stream.json")).report.route_counts

def test_media_payload_rejected():
 report=evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_media_payload_rejected.json")).report
 assert report.route_counts.get("blocked_by_policy",0)==1
 assert report.event_results[0].policy_chain_stages[0]["name"]=="media_payload_scan"
def test_digest_deterministic():
 a=evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_mixed_household_exterior_stream.json")).report.deterministic_digest
 b=evaluate_dry_run_session(load_session_fixture(f"{FIX}/dry_run_mixed_household_exterior_stream.json")).report.deterministic_digest
 assert a==b and len(a)==64
