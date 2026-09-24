from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.developmental_model_replacement_production_trial import (
    RECEIPT_SCHEMA, ProductionTrialError, _exact, _file_snapshot,
    verify_production_trial_receipt,
)
from sentientos.local_runtime_provisioning import semantic_digest

pytestmark = pytest.mark.no_legacy_skip


def test_exact_real_production_posture_one_trial_composition() -> None:
    source = Path("sentientos/developmental_model_replacement_production_trial.py").read_text()
    assert "campaign.run_next_trial()" in source
    assert source.count("campaign.run_next_trial()") == 1
    assert '"production_experimental_trial"' in source
    assert '"synthetic_test_trial"' in source
    assert '"autonomous_repetition_performed": False' in source
    assert all(term not in source for term in ("while ", "--all", "--repeat", "until-complete", "scheduler", "timer"))


def test_preflight_and_dual_worker_order_and_cleanup_are_fixed() -> None:
    source = Path("sentientos/developmental_model_replacement_production_trial.py").read_text()
    preflight = source.index("campaign, trial_id = self._preflight_campaign")
    identity_a = source.index("if evidence_a.cognitive_identity !=")
    approval_b = source.index("approval_b = verify_runtime_approval")
    load_a = source.index("endpoint_a = self._controller.establish")
    load_b = source.index("endpoint_b = self._controller.establish")
    execute = source.index("campaign.run_next_trial()")
    close_b = source.index("endpoint_b.close")
    close_a = source.index("endpoint_a.close")
    assert preflight < identity_a < approval_b < load_a < load_b < execute < close_b < close_a
    assert "finally:" in source


def test_canonical_and_history_snapshots_are_compared() -> None:
    source = Path("sentientos/developmental_model_replacement_production_trial.py").read_text()
    assert "before_activation != after_activation" in source
    assert "before_serving != after_serving" in source
    assert "before_history != context.history_record_set_digest" in source
    assert '"resident_default_model_preserved": True' in source
    assert '"activation" / "active.json"' in source and '"serving" / "active.json"' in source


def test_snapshot_proves_absence_or_exact_bytes(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    assert _file_snapshot(target) == {"state": "absent"}
    target.write_bytes(b"exact\n")
    snapshot = _file_snapshot(target)
    assert snapshot["state"] == "present" and snapshot["size_bytes"] == 6
    target.write_bytes(b"changed\n")
    assert _file_snapshot(target) != snapshot


@pytest.mark.parametrize("alias", ["", "current", "latest", "default", "any", "*"])
def test_aliases_are_rejected(alias: str) -> None:
    with pytest.raises(ProductionTrialError, match="not_exact"):
        _exact(alias, "identity")


def test_receipt_schema_and_tampering_detection() -> None:
    receipt = {"schema_version": RECEIPT_SCHEMA, "evidence_posture": "synthetic_test_trial",
               "autonomous_repetition_performed": False, "receipt_id": "production-model-replacement-trial-1"}
    receipt["receipt_digest"] = semantic_digest(receipt)
    verify_production_trial_receipt(receipt)
    receipt["autonomous_repetition_performed"] = True
    with pytest.raises(ProductionTrialError, match="tampered"):
        verify_production_trial_receipt(receipt)


def test_existing_campaign_and_five_condition_owners_are_reused() -> None:
    source = Path("sentientos/developmental_model_replacement_production_trial.py").read_text()
    assert "DevelopmentalModelReplacementCampaign.reconstruct" in source
    assert "DevelopmentalModelReplacementExperiment(" in source
    assert "CONDITION_ORDER" not in source


def test_no_identity_or_improvement_claims() -> None:
    source = Path("sentientos/developmental_model_replacement_production_trial.py").read_text().lower()
    assert all(term not in source for term in ("model b is better", "identity persisted", "selfhood", "consciousness"))
