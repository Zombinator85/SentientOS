from __future__ import annotations

from pathlib import Path

from sentientos.ethics.covenant_digest_daemon import CovenantDigestDaemon


def test_covenant_digest_captures_ethics_events(tmp_path: Path):
    workspace = tmp_path / "ethics"
    daemon = CovenantDigestDaemon(workspace)

    events = [
        {"category": "violation", "summary": "Unauthorized data export", "id": "viol-22"},
        {"category": "proposal", "summary": "Consent prompt upgrade", "id": "prop-19"},
        {"category": "consent_delta", "summary": "User revoked analytics", "id": "cons-03"},
        {"category": "drift_audit", "summary": "Found divergence in ritual logs", "id": "drift-99"},
    ]

    result = daemon.generate_digest(events, doctrine_hash="abc123", changed_terms=["consent", "retention"])

    digest_path = Path(result["digest_path"])
    snapshot_path = Path(result["snapshot_path"])
    assert digest_path.exists()
    assert snapshot_path.exists()

    digest_content = digest_path.read_text(encoding="utf-8")
    assert "Violations caught" in digest_content
    assert "Consent deltas" in digest_content
    assert "drift-99" in digest_content

    snapshot = snapshot_path.read_text(encoding="utf-8")
    assert "abc123" in snapshot
    assert "consent" in snapshot
