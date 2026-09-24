from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip
REPO = Path(__file__).parents[2]
SCRIPT = REPO / "scripts/run_resident_cognitive_model_serving_rehearsal.py"


def execute(tmp_path: Path, scenario: str) -> dict:
    env = dict(os.environ); env["PYTHONPATH"] = str(REPO)
    completed = subprocess.run([sys.executable, str(SCRIPT), "run", "--scenario", scenario,
        "--root", str(tmp_path / scenario), "--summary"], cwd=REPO, env=env, text=True,
        capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_cli_happy_uses_real_serving_bridge_and_cognition_owner(tmp_path: Path) -> None:
    result = execute(tmp_path, "happy")
    observed = result["result"]
    assert result["status"] == "verified_complete"
    assert result["evidence_posture"] == "synthetic_rehearsal" and result["production_evidence"] is False
    assert observed["establishment_inference_count"] == 0 and observed["worker_calls"] >= 2
    assert observed["cognition_observation_ids"] and observed["cycle_writeback_receipt_id"]
    assert observed["model_serving_admission_ref"] != observed["inference_receipts"][-1]["admission_decision_ref"]
    assert observed["activation_a_digest"] == result["canonical_activation_final_digest"]


def test_activation_change_invalidates_without_successor_or_fallback(tmp_path: Path) -> None:
    result = execute(tmp_path, "activation-change")["result"]
    assert result["activation_a_digest"] != result["activation_b_digest"]
    assert result["model_serving_admission_count"] == 1
    assert result["worker_close_count"] == 1 and result["b_construction_count"] == result["fallback_count"] == 0
    assert result["canonical_b_preserved"] is True and result["final_health"] == "closed"


def test_production_chat_and_resident_custody_are_independent(tmp_path: Path) -> None:
    result = execute(tmp_path, "production-chat-coexistence")["result"]
    assert result["resident_session_id"] != result["chat_session_id"]
    assert result["model_serving_admission_ref"] != result["chat_model_serving_admission_ref"]
    assert result["resident_receipt_root"] != result["chat_receipt_root"]
    assert result["chat_current_after_resident_close"] is True
    assert result["chat_custody_unchanged"] is True and result["resident_close_chat_invalidation_count"] == 0


def test_synthetic_posture_cannot_serialize_as_production(tmp_path: Path) -> None:
    result = execute(tmp_path, "happy")
    raw = json.dumps(result, sort_keys=True)
    assert '"evidence_posture": "synthetic_rehearsal"' in raw
    assert '"production_evidence": true' not in raw
    assert "production_experimental_trial" not in raw
