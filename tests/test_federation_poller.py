import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.federation.config import FederationConfig, PeerConfig
from sentientos.federation.delta import DeltaResult
from sentientos.federation.identity import NodeId
from sentientos.federation.poller import FederationPoller, PeerReplaySnapshot
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



def _replay_snapshot_poller(tmp_path, logs):
    return FederationPoller(
        FederationConfig(
            enabled=True,
            node_id=NodeId(name="local", fingerprint="fp-local"),
            state_file=str(tmp_path / "runtime" / "federation" / "state" / "local.json"),
            peers=[],
            poll_interval_seconds=1,
            max_drift_peers=0,
            max_incompatible_peers=0,
            max_missing_peers=0,
        ),
        runtime=object(),
        log_cb=logs.append,
    )


def _replay_snapshot(peer):
    return PeerReplaySnapshot(
        peer=peer,
        severity="none",
        delta=DeltaResult(severity="none"),
        last_seen=datetime.now(timezone.utc),
    )


@pytest.mark.no_legacy_skip
def test_persist_replay_snapshot_rejects_path_traversal(tmp_path):
    logs = []
    poller = _replay_snapshot_poller(tmp_path, logs)
    escaped = poller._replay_dir.parent / "outside.json"

    poller._persist_replay_snapshot(_replay_snapshot("../outside"))

    assert not escaped.exists()
    assert any("Rejected unsafe federation replay peer name" in message for message in logs)


@pytest.mark.no_legacy_skip
def test_persist_replay_snapshot_keeps_safe_peer_name(tmp_path):
    logs = []
    poller = _replay_snapshot_poller(tmp_path, logs)
    target = poller._replay_dir / "peer-one.json"

    poller._persist_replay_snapshot(_replay_snapshot("peer-one"))

    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8"))["peer"] == "peer-one"
    assert poller._load_persisted_replay()["peer-one"].peer == "peer-one"


@pytest.mark.no_legacy_skip
def test_load_persisted_replay_rejects_filename_payload_mismatch(tmp_path):
    logs = []
    poller = _replay_snapshot_poller(tmp_path, logs)
    payload = _replay_snapshot("../outside").to_payload()
    (poller._replay_dir / "configured-peer.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    assert poller._load_persisted_replay() == {}


@pytest.mark.no_legacy_skip
def test_replay_snapshot_rejects_symlinked_replay_directory(tmp_path):
    logs = []
    poller = _replay_snapshot_poller(tmp_path, logs)
    replay_dir = poller._replay_dir
    outside = tmp_path / "outside"
    outside.mkdir()
    replay_dir.rmdir()
    replay_dir.symlink_to(outside, target_is_directory=True)
    (outside / "peer-one.json").write_text(
        json.dumps(_replay_snapshot("peer-one").to_payload()), encoding="utf-8"
    )

    poller._persist_replay_snapshot(_replay_snapshot("peer-one"))

    assert poller._load_persisted_replay() == {}
    assert json.loads((outside / "peer-one.json").read_text(encoding="utf-8"))["peer"] == "peer-one"
    assert any("Rejected unsafe federation replay directory" in message for message in logs)
