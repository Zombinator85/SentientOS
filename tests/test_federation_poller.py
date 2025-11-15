from datetime import datetime, timezone
from pathlib import Path

from sentientos.federation.config import FederationConfig, PeerConfig
from sentientos.federation.identity import NodeId
from sentientos.federation.poller import FederationPoller
from sentientos.federation.summary import CathedralState, ConfigState, ExperimentState, FederationSummary


def _summary(node: str, digest: str, ledger: int = 5) -> FederationSummary:
    return FederationSummary(
        node_name=node,
        fingerprint=f"fp-{node}",
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id="amend-1",
            last_applied_digest=digest,
            ledger_height=ledger,
            rollback_count=0,
        ),
        experiments=ExperimentState(total=1, chains=0, dsl_version="1.0"),
        config=ConfigState(config_digest=f"cfg-{digest}"),
        meta={},
    )


def test_poller_updates_state(tmp_path, monkeypatch):
    writes = []
    events = []
    logs = []

    local_summary = _summary("local", "dg-local")
    peer_ok = _summary("peer-ok", "dg-local")
    peer_drift = _summary("peer-drift", "dg-peer", ledger=7)

    from sentientos.federation import poller as poller_module

    monkeypatch.setattr(poller_module, "publish_event", lambda event: events.append(event))
    monkeypatch.setattr(poller_module, "build_local_summary", lambda runtime: local_summary)
    monkeypatch.setattr(
        poller_module,
        "write_local_summary",
        lambda summary, path: writes.append((summary, Path(path))),
    )

    peer_map = {
        "peer_ok.json": peer_ok,
        "peer_drift.json": peer_drift,
    }

    def _read_peer(path: str):
        name = Path(path).name
        return peer_map.get(name)

    monkeypatch.setattr(poller_module, "read_peer_summary", _read_peer)

    config = FederationConfig(
        enabled=True,
        node_id=NodeId(name="local", fingerprint="fp-local"),
        state_file=str(tmp_path / "local.json"),
        peers=[
            PeerConfig(node_name="peer-ok", state_file=str(tmp_path / "peer_ok.json")),
            PeerConfig(node_name="peer-drift", state_file=str(tmp_path / "peer_drift.json")),
            PeerConfig(node_name="peer-missing", state_file=str(tmp_path / "missing.json")),
        ],
        poll_interval_seconds=1,
    )

    poller = FederationPoller(config, runtime=object(), log_cb=logs.append)
    poller._poll_once()

    assert writes and writes[0][1] == Path(config.state_file)

    state = poller.state
    counts = state.counts()
    assert counts["total"] == 3
    assert counts["healthy"] == 1
    assert counts["drift"] == 1
    assert counts["incompatible"] == 1
    assert state.peer_reports["peer-ok"].level == "ok"
    assert state.peer_reports["peer-drift"].level == "drift"
    assert state.peer_reports["peer-missing"].level == "incompatible"

    assert any("drift detected" in message for message in logs)
    assert any("now incompatible" in message for message in logs)

    assert any(event.get("kind") == "federation" for event in events)
