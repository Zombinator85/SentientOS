from __future__ import annotations

from sentientos.repair_outcome import verify_repair_outcome


def test_repair_outcome_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = verify_repair_outcome(anomaly_kind="x", pre_details={"symptom_cleared": True})
    assert out.status in {"verified", "unverified"}
    assert (tmp_path / "glow/repairs/repair_outcomes.jsonl").exists()
