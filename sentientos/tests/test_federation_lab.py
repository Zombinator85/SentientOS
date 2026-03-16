from __future__ import annotations

import json
from pathlib import Path

from sentientos.lab import deterministic_node_layout, list_federation_lab_scenarios, run_live_federation_lab
from sentientos.ops import main as ops_main


def test_deterministic_layout_stable() -> None:
    first = deterministic_node_layout(nodes=3, seed=42)
    second = deterministic_node_layout(nodes=3, seed=42)
    assert first == second
    assert [row.node_id for row in first] == ["node-01", "node-02", "node-03"]


def test_scenario_list_contains_required_live_cases() -> None:
    rows = list_federation_lab_scenarios()
    names = {row["name"] for row in rows}
    assert {"healthy_3node", "quorum_failure", "replay_storm", "reanchor_continuation", "pressure_local_safety"}.issubset(names)
    assert all(bool(row.get("daemon_parity")) for row in rows)


def test_ops_lab_list_scenarios_json(tmp_path: Path, capsys) -> None:
    rc = ops_main(["--repo-root", str(tmp_path), "lab", "federation", "--list-scenarios", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sentientos.ops"
    assert payload["command"] == "lab.federation"


def test_live_lab_run_emits_manifest_in_worker_mode(tmp_path: Path) -> None:
    payload = run_live_federation_lab(tmp_path, scenario_name="healthy_3node", seed=7, node_count=2, runtime_s=0.3, clean=True, runtime_mode="worker")
    assert payload["mode"] == "live_lab"
    assert payload["runtime_mode_resolved"] == "worker"
    run_root = tmp_path / payload["artifact_paths"]["run_root"]
    manifest_path = run_root / "artifact_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["file_count"] > 0


def test_live_lab_daemon_mode_emits_lifecycle_artifacts(tmp_path: Path) -> None:
    payload = run_live_federation_lab(tmp_path, scenario_name="healthy_3node", seed=8, node_count=2, runtime_s=0.2, clean=True, runtime_mode="daemon")
    run_root = tmp_path / payload["artifact_paths"]["run_root"]
    transitions = run_root / "process_transitions.jsonl"
    assert payload["runtime_mode_resolved"] == "daemon"
    assert transitions.exists()
    rows = [json.loads(line) for line in transitions.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(row.get("state") == "running" for row in rows)
    assert any(row.get("state") in {"stopped", "timeout"} for row in rows)


def test_ops_lab_mode_argument_routes_runtime(tmp_path: Path, capsys) -> None:
    rc = ops_main(
        [
            "--repo-root",
            str(tmp_path),
            "lab",
            "federation",
            "--scenario",
            "healthy_3node",
            "--nodes",
            "2",
            "--seed",
            "7",
            "--runtime-s",
            "0.2",
            "--mode",
            "worker",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime_mode_requested"] == "worker"
    assert payload["runtime_mode_resolved"] == "worker"
