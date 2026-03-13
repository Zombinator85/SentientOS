from __future__ import annotations

from scripts.emit_contract_status import emit_contract_status


def test_contract_status_reports_federated_enforcement_policy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "ci-advisory")
    payload = emit_contract_status(tmp_path / "glow/contracts/contract_status.json")
    policy = payload.get("federated_enforcement_policy")
    assert isinstance(policy, dict)
    assert policy.get("profile") == "ci-advisory"
    domain = next(item for item in payload["contracts"] if item["domain_name"] == "federated_enforcement_calibration")
    assert domain["profile"] == "ci-advisory"
    assert "postures" in domain
