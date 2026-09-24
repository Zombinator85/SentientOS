from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import pytest

from sentientos.developmental_model_replacement_rehearsal import prepare, run_next, verify

pytestmark = pytest.mark.no_legacy_skip
REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/run_developmental_model_replacement_rehearsal.py"

def cli(root: Path, command: str, *extra: str) -> dict[str, object]:
    environment = {**os.environ, "PYTHONPATH": str(REPO)}
    result = subprocess.run([sys.executable, str(SCRIPT), command, "--root", str(root), "--summary", *extra],
        cwd=REPO, env=environment, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)

def test_separate_cli_processes_reconstruct_and_complete_exact_campaign(tmp_path: Path) -> None:
    root = tmp_path / "happy"
    prepared = cli(root, "prepare")
    assert prepared["expected_trial_ids"] == ["rehearsal-trial-1", "rehearsal-trial-2"]
    initial = cli(root, "verify")
    assert initial["completed_trial_ids"] == [] and initial["next_trial_id"] == "rehearsal-trial-1"
    first = cli(root, "run-next")
    assert first["receipt"]["trial_id"] == "rehearsal-trial-1"
    after_first = cli(root, "verify")
    assert after_first["completed_trial_ids"] == ["rehearsal-trial-1"]
    assert after_first["next_trial_id"] == "rehearsal-trial-2" and len(after_first["inference_receipts"]) == 5
    second = cli(root, "run-next")
    assert second["receipt"]["trial_id"] == "rehearsal-trial-2"
    summary = cli(root, "summarize"); final = cli(root, "verify")
    assert summary["completed_valid_trial_count"] == 2
    assert final["status"] == "verified_complete" and len(final["inference_receipts"]) == 10
    assert len(final["serving_receipts"]) == len(final["closure_receipts"]) == 4
    assert final["synthetic_only_posture"] and final["activation_preserved"]
    assert final["production_serving_preserved"] and final["developmental_history_preserved"]

def test_model_b_load_failure_closes_a_without_trial_success(tmp_path: Path) -> None:
    root = tmp_path / "load-failure"; prepare(root, fault="model_b_load_failure")
    with pytest.raises(Exception, match="experimental_model_load_failed"): run_next(root)
    bundle = root / "rehearsal"; state = next((bundle / "developmental_experiments/model_replacement_campaigns/state").glob("*.json"))
    assert json.loads(state.read_text())["completed_trials"] == []
    assert not (bundle / "trial_receipts").exists()
    receipts = list((root / "installation/installations/model-rehearsal/state/local-model/developmental-model-replacement/experimental-serving/receipts").glob("*.json"))
    assert sum("closure" in path.name for path in receipts) == 1

def test_loaded_identity_drift_closes_worker_before_inference(tmp_path: Path) -> None:
    root = tmp_path / "identity-drift"; prepare(root, fault="loaded_identity_drift")
    with pytest.raises(Exception, match="loaded_cognitive_identity_mismatch"): run_next(root)
    inference = root / "installation/installations/model-rehearsal/state/local-model/developmental-model-replacement/experimental-serving/inference"
    assert not inference.exists() or not list(inference.rglob("*.json"))

def test_protocol_tamper_fails_before_worker_construction(tmp_path: Path) -> None:
    root = tmp_path / "protocol-tamper"; scenario = prepare(root)
    protocol = root / "rehearsal/developmental_experiments/model_replacement/protocols" / f"{scenario['protocol_id']}.json"
    value = json.loads(protocol.read_text()); value["inference_purpose"] = "tampered"; protocol.write_text(json.dumps(value))
    with pytest.raises(Exception, match="protocol"): run_next(root)
    serving = root / "installation/installations/model-rehearsal/state/local-model/developmental-model-replacement/experimental-serving"
    assert not list(serving.rglob("experimental-serving-receipt-*.json"))

def test_campaign_state_tamper_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "state-tamper"; scenario = prepare(root)
    state = root / "rehearsal/developmental_experiments/model_replacement_campaigns/state" / f"{scenario['campaign_id']}.json"
    value = json.loads(state.read_text()); value["next_trial_id"] = "rehearsal-trial-2"; state.write_text(json.dumps(value))
    with pytest.raises(Exception, match="campaign_state_tampered"): verify(root)

def test_currentness_failure_invalidates_without_retry(tmp_path: Path) -> None:
    root = tmp_path / "currentness"; prepare(root, fault="inference_currentness_failure")
    with pytest.raises(Exception, match="currentness|identity|endpoint_closed"): run_next(root)
    state_path = next((root / "rehearsal/developmental_experiments/model_replacement_campaigns/state").glob("*.json"))
    state = json.loads(state_path.read_text())
    assert state["validity"] == "invalid_incomplete" and state["failure_reason"] == "campaign_trial_failed_no_retry"
    with pytest.raises(Exception, match="campaign_(not_runnable|interrupted_during_trial)"): run_next(root)
    assert json.loads(state_path.read_text())["validity"] == "invalid_incomplete"
    assert not (root / "rehearsal/trial_receipts").exists()

def test_rehearsal_cannot_be_labeled_production_evidence(tmp_path: Path) -> None:
    root = tmp_path / "posture"; prepare(root); result = run_next(root)
    receipt = dict(result["receipt"]); receipt["evidence_posture"] = "production_experimental_trial"
    receipt["receipt_digest"] = "forged"
    from sentientos.developmental_model_replacement_production_trial import verify_production_trial_receipt
    with pytest.raises(Exception, match="tampered"): verify_production_trial_receipt(receipt)
