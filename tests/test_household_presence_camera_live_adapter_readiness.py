from pathlib import Path
from sentientos.household_presence_camera_live_adapter_readiness import build_default_policy,validate_policy,evaluate_readiness,dumps_result

def test_default_policy_validates(): assert validate_policy(build_default_policy())["ok"]
def test_ready_fixture_not_live_ready():
 r=evaluate_readiness({"workspace_root":".","fixtures_dir":"tests/fixtures/household_presence_camera_live_adapter_readiness","risk_flags":{"operator_review_required":True}}).report
 assert r.status in {"ready_for_stub_only","ready_for_operator_review"}
 assert r.status!="ready_for_design"
def test_missing_policy_chain_blocks(): assert evaluate_readiness({"workspace_root":".","simulate_missing":["policy_chain"]}).report.status=="blocked_missing_policy_chain"
def test_missing_zone_config_blocks(): assert evaluate_readiness({"workspace_root":".","simulate_missing":["zone_config"]}).report.status=="blocked_missing_zone_config"
def test_risks_block():
 assert evaluate_readiness({"workspace_root":".","risk_flags":{"live_runtime_risk_present":True}}).report.status=="blocked_live_runtime_risk"
 assert evaluate_readiness({"workspace_root":".","risk_flags":{"talkback_boundary_risk":True}}).report.status=="blocked_speaker_boundary"
 assert evaluate_readiness({"workspace_root":".","risk_flags":{"external_authority_risk":True}}).report.status=="blocked_external_authority_boundary"
def test_deterministic_digest():
 a=evaluate_readiness({"workspace_root":"."}).report.deterministic_digest
 b=evaluate_readiness({"workspace_root":"."}).report.deterministic_digest
 assert a==b and len(a)==64
 assert "open_camera_now" in dumps_result(evaluate_readiness({"workspace_root":"."}))
