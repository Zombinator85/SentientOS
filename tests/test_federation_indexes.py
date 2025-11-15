import json
from pathlib import Path

import pytest

from sentientos.cathedral.digest import CathedralDigest
from sentientos.federation.config import FederationConfig, PeerConfig
from sentientos.federation.identity import NodeId
from sentientos.federation.summary import (
    build_cathedral_index,
    build_experiment_index,
    build_local_summary,
)


class _LedgerStub:
    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path


class _RuntimeStub:
    def __init__(self, runtime_root: Path, ledger_path: Path, federation_cfg: FederationConfig) -> None:
        self._config = {"runtime": {"root": str(runtime_root)}}
        self._runtime_root = runtime_root
        self._cathedral_digest = CathedralDigest()
        self._amendment_applicator = _LedgerStub(ledger_path)
        self._federation_config = federation_cfg

    @property
    def config(self) -> dict:
        return self._config

    @property
    def runtime_root(self) -> Path:
        return self._runtime_root

    @property
    def cathedral_digest(self) -> CathedralDigest:
        return self._cathedral_digest

    @property
    def federation_config(self) -> FederationConfig:
        return self._federation_config


def _federation_config(tmp_path: Path, **overrides) -> FederationConfig:
    return FederationConfig(
        enabled=True,
        node_id=NodeId(name="local", fingerprint="fp-local"),
        state_file=str(tmp_path / "state" / "local.json"),
        peers=[PeerConfig(node_name="peer-a", state_file=str(tmp_path / "peer-a.json"))],
        poll_interval_seconds=5,
        max_drift_peers=0,
        max_incompatible_peers=0,
        max_missing_peers=0,
        max_cathedral_ids=overrides.get("max_cathedral_ids", 0),
        max_experiment_ids=overrides.get("max_experiment_ids", 0),
    )


def test_cathedral_index_respects_limit(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    entries = [
        {"ts": "2024-01-01T00:00:00Z", "amendment_id": f"A{idx}", "digest": f"dg{idx}"}
        for idx in range(1, 6)
    ]
    entries.append({"ts": "2024-01-02T00:00:00Z", "event": "rollback", "amendment_id": "A3"})
    ledger_path.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")
    runtime = _RuntimeStub(tmp_path, ledger_path, _federation_config(tmp_path, max_cathedral_ids=2))

    index = build_cathedral_index(runtime, 2)
    assert index is not None
    assert index.applied_ids == ["A4", "A5"]
    assert index.applied_digests == ["dg4", "dg5"]
    assert index.height == len(entries)


def test_experiment_index_tracks_runs_and_chains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chain_log = tmp_path / "chains.jsonl"
    chain_entries = [
        {"event": "chain_complete", "chain_id": "alpha", "outcome": "success"},
        {"event": "chain_complete", "chain_id": "beta", "outcome": "aborted_limit"},
    ]
    chain_log.write_text("\n".join(json.dumps(entry) for entry in chain_entries), encoding="utf-8")

    experiments = [
        {"id": "exp-10", "triggers": 3, "success": 2, "proposed_at": "2024-01-01T00:00:00Z"},
        {"id": "exp-11", "triggers": 1, "success": 1, "proposed_at": "2024-01-02T00:00:00Z"},
        {"id": "exp-12", "triggers": 0, "success": 0, "proposed_at": "2024-01-03T00:00:00Z"},
    ]

    from sentientos.federation import summary as summary_module

    monkeypatch.setattr(summary_module, "CHAIN_LOG_PATH", chain_log)
    monkeypatch.setattr(summary_module.experiment_tracker, "list_experiments", lambda: experiments)

    runtime = _RuntimeStub(tmp_path, tmp_path / "ledger.jsonl", _federation_config(tmp_path, max_experiment_ids=2))
    index = build_experiment_index(runtime, 2)
    assert index is not None
    assert index.runs == {"total": 4, "successful": 3, "failed": 1}
    assert index.chains == {"total": 2, "completed": 1, "aborted": 1}
    assert index.latest_ids == ["exp-11", "exp-12"]


def test_summary_omits_indexes_when_limits_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text("", encoding="utf-8")
    runtime = _RuntimeStub(tmp_path, ledger_path, _federation_config(tmp_path, max_cathedral_ids=0, max_experiment_ids=0))
    monkeypatch.setattr(
        "sentientos.federation.summary.experiment_tracker.list_experiments",
        lambda: [],
    )

    summary = build_local_summary(runtime)
    assert summary.indexes is None
