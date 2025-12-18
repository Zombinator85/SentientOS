from pathlib import Path

from sentientos.ethics.consent_memory_vault import ConsentMemoryVault


def test_consent_memory_vault_tracks_permissions(tmp_path: Path):
    vault = ConsentMemoryVault(tmp_path / "consent_log.jsonl")

    vault.log_consent("emotional modeling", status="granted", context="Session 1")
    vault.log_consent("emotional modeling", status="denied", context="Session 2 revision")
    vault.withdraw("data export", context="Operator requested stop")

    assert vault.ever_granted("emotional modeling") is True
    latest = vault.query("emotional modeling")
    assert latest["status"] == "denied"

    snapshot = vault.snapshot()
    assert len(snapshot) >= 3

    structured = vault.query("data export")
    assert structured["status"] == "denied"
    assert "retroactive withdrawal" in structured["context"]
