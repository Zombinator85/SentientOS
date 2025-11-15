import json
import subprocess
import sys
from datetime import datetime, timezone

from sentientos.federation.summary import (
    CathedralIndexSnapshot,
    CathedralState,
    ConfigState,
    ExperimentIndexSnapshot,
    ExperimentState,
    FederationSummary,
    SummaryIndexes,
    write_local_summary,
)


def _summary(node: str, ids, digest: str, latest_experiments) -> FederationSummary:
    return FederationSummary(
        node_name=node,
        fingerprint=f"fp-{node}",
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id=ids[-1] if ids else "",
            last_applied_digest=digest,
            ledger_height=len(ids),
            rollback_count=0,
        ),
        experiments=ExperimentState(total=len(latest_experiments), chains=0, dsl_version="1.0"),
        config=ConfigState(config_digest="cfg"),
        meta={},
        indexes=SummaryIndexes(
            cathedral=CathedralIndexSnapshot(applied_ids=ids, applied_digests=[], height=len(ids)),
            experiments=ExperimentIndexSnapshot(
                runs={"total": len(latest_experiments), "successful": len(latest_experiments), "failed": 0},
                chains={"total": 0, "completed": 0, "aborted": 0},
                latest_ids=latest_experiments,
            ),
        ),
    )


def test_cli_sync_view_outputs_peer_status(tmp_path, monkeypatch):
    base_dir = tmp_path
    monkeypatch.setenv("SENTIENTOS_BASE_DIR", str(base_dir))
    config_dir = base_dir / "sentientos_data" / "config"
    config_dir.mkdir(parents=True)
    state_dir = base_dir / "federation" / "state"
    state_dir.mkdir(parents=True)

    local_state = state_dir / "local.json"
    peer_state = state_dir / "peer-a.json"

    local_summary = _summary("LOCAL", ["A1"], "dg-local", ["exp-1"])
    peer_summary = _summary("PEER-A", ["A1", "A2"], "dg-peer", ["exp-1", "exp-2"])
    write_local_summary(local_summary, str(local_state))
    write_local_summary(peer_summary, str(peer_state))

    config = {
        "runtime": {"root": str(base_dir)},
        "federation": {
            "enabled": True,
            "node_name": "LOCAL",
            "state_file": str(local_state),
            "poll_interval_seconds": 5,
            "indexes": {"max_cathedral_ids": 64, "max_experiment_ids": 32},
            "peers": [
                {"node_name": "PEER-A", "state_file": str(peer_state)},
            ],
        },
    }
    config_path = config_dir / "runtime.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "sentientos.federation", "sync-view"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Peer: PEER-A" in result.stdout
    assert "Cathedral: AHEAD_OF_ME" in result.stdout
