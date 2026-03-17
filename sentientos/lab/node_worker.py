from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path

from sentientos.attestation import iso_now, write_json
from sentientos.lab.node_truth_artifacts import emit_node_truth_artifacts
from sentientos.node_operations import node_health


def _append_log(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def run(node_root: Path, *, node_id: str, host_id: str, heartbeat_s: float) -> int:
    stop = False

    def _signal_handler(_signum: int, _frame: object | None) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    runtime_log = node_root / "glow/lab/runtime_log.jsonl"
    heartbeat_path = node_root / "glow/lab/heartbeat.json"
    while not stop:
        health = node_health(node_root)
        row = {
            "schema_version": 1,
            "ts": iso_now(),
            "node_id": node_id,
            "host_id": host_id,
            "health_state": health.get("health_state"),
            "constitution_state": health.get("constitution_state"),
            "integrity_overall": health.get("integrity_overall"),
        }
        _append_log(runtime_log, row)
        write_json(heartbeat_path, row)
        emit_node_truth_artifacts(node_root, node_id=node_id, host_id=host_id)
        time.sleep(max(0.2, heartbeat_s))

    _append_log(runtime_log, {"schema_version": 1, "ts": iso_now(), "node_id": node_id, "host_id": host_id, "event": "stopped"})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentientOS live federation lab worker")
    parser.add_argument("--node-root", required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--host-id", default="")
    parser.add_argument("--heartbeat-s", type=float, default=1.0)
    args = parser.parse_args(argv)
    return run(Path(args.node_root).resolve(), node_id=str(args.node_id), host_id=str(args.host_id), heartbeat_s=float(args.heartbeat_s))


if __name__ == "__main__":
    raise SystemExit(main())
