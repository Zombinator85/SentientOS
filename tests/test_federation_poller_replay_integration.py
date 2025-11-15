from datetime import datetime, timezone
from pathlib import Path

from sentientos.federation.config import FederationConfig, PeerConfig
from sentientos.federation.identity import NodeId
from sentientos.federation.poller import FederationPoller
from sentientos.federation.summary import (
    CathedralState,
    ConfigState,
    ExperimentState,
    FederationSummary,
)


class _RuntimeStub:
    def get_persona_snapshot(self):  # pragma: no cover - simple data
        return {"mood": "calm"}

    def get_dream_snapshot(self):  # pragma: no cover - simple data
        return {"last_focus": "alignment"}


def _summary(digest: str, total: int) -> FederationSummary:
    return FederationSummary(
        node_name="node",
        fingerprint="fp-node",
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id="amend-1",
            last_applied_digest=digest,
            ledger_height=2,
            rollback_count=0,
        ),
        experiments=ExperimentState(total=total, chains=0, dsl_version="1.0"),
        config=ConfigState(config_digest=f"cfg-{digest}"),
        meta={"runtime_root": "/tmp"},
    )


def test_poller_records_replay_delta(tmp_path, monkeypatch):
    events = []

    local_summary = _summary("dg-local", 2)
    peer_summary = _summary("dg-peer", 3)

    from sentientos.federation import poller as poller_module

    monkeypatch.setattr(poller_module, "publish_event", lambda event: events.append(event))
    monkeypatch.setattr(poller_module, "build_local_summary", lambda runtime: local_summary)
    monkeypatch.setattr(poller_module, "read_peer_summary", lambda path: peer_summary)

    state_file = tmp_path / "federation" / "state" / "local.json"
    peer_state = tmp_path / "federation" / "state" / "peer.json"
    peer_state.parent.mkdir(parents=True, exist_ok=True)
    peer_state.write_text("{}", encoding="utf-8")

    config = FederationConfig(
        enabled=True,
        node_id=NodeId(name="local", fingerprint="fp-local"),
        state_file=str(state_file),
        peers=[PeerConfig(node_name="peer", state_file=str(peer_state))],
        poll_interval_seconds=1,
        max_drift_peers=0,
        max_incompatible_peers=0,
        max_missing_peers=0,
    )

    poller = FederationPoller(config, runtime=_RuntimeStub(), log_cb=lambda *_: None)
    poller._poll_once()

    replay_state = poller.get_replay_state()
    assert "peer" in replay_state
    assert replay_state["peer"].severity in {"medium", "high"}

    replay_file = tmp_path / "federation" / "replay" / "peer.json"
    assert replay_file.exists()

    assert any(event.get("kind") == "federation_replay" for event in events)
