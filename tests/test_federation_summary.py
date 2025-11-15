import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.cathedral.digest import CathedralDigest
from sentientos.federation.config import FederationConfig, PeerConfig
from sentientos.federation.identity import NodeId
from sentientos.federation.summary import (
    build_local_summary,
    read_peer_summary,
    summary_digest,
    write_local_summary,
)


class _AmendmentStub:
    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path


class _RuntimeStub:
    def __init__(self, config: dict, runtime_root: Path, digest: CathedralDigest, federation_cfg: FederationConfig, ledger: Path) -> None:
        self._config = config
        self._runtime_root = runtime_root
        self._cathedral_digest = digest
        self._amendment_applicator = _AmendmentStub(ledger)
        self._federation_config = federation_cfg

    @property
    def cathedral_digest(self) -> CathedralDigest:
        return self._cathedral_digest

    @property
    def federation_config(self) -> FederationConfig:
        return self._federation_config

    @property
    def runtime_root(self) -> Path:
        return self._runtime_root

    @property
    def config(self) -> dict:
        return self._config


@pytest.fixture
def runtime_fixture(tmp_path: Path, monkeypatch):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_entries = [
        {"ts": "2024-01-01T00:00:00Z", "digest": "dg1"},
        {"ts": "2024-01-02T00:00:00Z", "digest": "dg2"},
    ]
    ledger_path.write_text("\n".join(json.dumps(entry) for entry in ledger_entries), encoding="utf-8")

    chain_log_path = tmp_path / "chain.jsonl"
    chain_log_entries = [
        {"chain_id": "alpha"},
        {"chain_id": "beta"},
        {"chain_id": "alpha", "event": "chain_complete"},
    ]
    chain_log_path.write_text("\n".join(json.dumps(entry) for entry in chain_log_entries), encoding="utf-8")

    from sentientos.federation import summary as summary_module
    from sentientos.experiments import runner as runner_module

    monkeypatch.setattr(summary_module.experiment_tracker, "list_experiments", lambda: [{"id": 1}, {"id": 2}])
    monkeypatch.setattr(runner_module, "CHAIN_LOG_PATH", chain_log_path)

    federation_cfg = FederationConfig(
        enabled=True,
        node_id=NodeId(name="APRIL-PC01", fingerprint="abcd1234"),
        state_file=str(tmp_path / "state" / "local.json"),
        peers=[PeerConfig(node_name="peer-a", state_file=str(tmp_path / "peer.json"))],
        poll_interval_seconds=5,
    )
    digest = CathedralDigest(
        accepted=1,
        applied=1,
        quarantined=0,
        rollbacks=2,
        auto_reverts=0,
        last_applied_id="amend-1",
    )
    config = {"runtime": {"root": str(tmp_path), "watchdog_interval": 5}}
    runtime = _RuntimeStub(config, tmp_path, digest, federation_cfg, ledger_path)
    return runtime


def test_build_local_summary_stable_digest(runtime_fixture, monkeypatch):
    summary1 = build_local_summary(runtime_fixture)
    summary2 = build_local_summary(runtime_fixture)
    assert summary_digest(summary1) == summary_digest(summary2)
    assert summary1.cathedral.ledger_height == 2
    assert summary1.cathedral.last_applied_digest == "dg2"
    assert summary1.experiments.total == 2
    assert summary1.experiments.chains == 2


def test_summary_round_trip(runtime_fixture, tmp_path: Path):
    summary = build_local_summary(runtime_fixture)
    state_path = tmp_path / "summary.json"
    write_local_summary(summary, str(state_path))
    loaded = read_peer_summary(str(state_path))
    assert loaded is not None
    assert loaded.node_name == summary.node_name
    assert loaded.cathedral.ledger_height == summary.cathedral.ledger_height
    assert loaded.config.config_digest == summary.config.config_digest


def test_digest_mismatch_detected(runtime_fixture, tmp_path: Path):
    summary = build_local_summary(runtime_fixture)
    state_path = tmp_path / "bad.json"
    write_local_summary(summary, str(state_path))
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["digest"] = "broken"
    state_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    result = read_peer_summary(str(state_path))
    assert result is None
