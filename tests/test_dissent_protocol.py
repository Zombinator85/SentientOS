from datetime import datetime, timedelta
from pathlib import Path

from sentientos.federation.dissent_protocol import FederatedDissentProtocol


def test_dissent_quarantine_and_alert(tmp_path: Path) -> None:
    protocol = FederatedDissentProtocol(quarantine_after_hours=1, now=datetime(2025, 1, 1, 12, 0, 0))
    local_state = {"glossary": "v1", "doctrine_digest": "alpha", "symbolic_merges": ["x"]}
    remote_state = {"glossary": "v2", "doctrine_digest": "alpha", "symbolic_merges": ["x", "y"]}

    created_at = protocol.now - timedelta(hours=2)
    destination = tmp_path / "integration" / "federation_dissent_event.jsonl"

    event = protocol.evaluate(local_state, remote_state, destination, created_at=created_at)

    assert event.quarantined is True
    assert event.alert is True
    assert event.override_vote is True
    assert event.disagreements

    lines = destination.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
