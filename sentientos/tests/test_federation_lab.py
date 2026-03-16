from __future__ import annotations

import json
from pathlib import Path

from sentientos.lab import (
    classify_convergence,
    deterministic_fault_schedule,
    deterministic_node_layout,
    list_federation_lab_scenarios,
    run_live_federation_lab,
)
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
    assert {
        "daemon_endurance_steady_state",
        "daemon_restart_storm_recovery",
        "daemon_reanchor_recovery_chain",
        "daemon_digest_mismatch_containment",
        "daemon_epoch_rotation_propagation",
        "daemon_pressure_fairness_endurance",
    }.issubset(names)
    assert all(bool(row.get("daemon_parity")) for row in rows)


def test_fault_schedule_deterministic_and_bounded() -> None:
    node_ids = ["node-01", "node-02", "node-03"]
    first = deterministic_fault_schedule(
        scenario_name="daemon_restart_storm_recovery",
        seed=91,
        node_ids=node_ids,
        duration_s=5.0,
    )
    second = deterministic_fault_schedule(
        scenario_name="daemon_restart_storm_recovery",
        seed=91,
        node_ids=node_ids,
        duration_s=5.0,
    )
    assert first == second
    assert all(0.0 <= float(row["offset_s"]) <= 5.0 for row in first)


def test_oracle_classification_matrix() -> None:
    converged = classify_convergence(
        expected={"quorum_admit": True},
        observed={"quorum_admit": True, "corridor_interpretable": True},
        checks={"runtime_boot_behavior": True, "quorum_behavior": True, "continuation_behavior": True, "epoch_behavior": True},
    )
    assert converged == "converged_expected"

    degraded = classify_convergence(
        expected={"quorum_admit": True},
        observed={"quorum_admit": True, "corridor_interpretable": True},
        checks={"runtime_boot_behavior": True, "quorum_behavior": True, "continuation_behavior": True, "epoch_behavior": True, "fairness_behavior": False},
    )
    assert degraded == "converged_with_degradation"

    failed = classify_convergence(
        expected={"quorum_admit": True},
        observed={"quorum_admit": False, "corridor_interpretable": True},
        checks={"runtime_boot_behavior": False, "quorum_behavior": False, "continuation_behavior": True, "epoch_behavior": True},
    )
    assert failed == "failed_to_converge"


def test_ops_lab_list_scenarios_json(tmp_path: Path, capsys) -> None:
    rc = ops_main(["--repo-root", str(tmp_path), "lab", "federation", "--list-scenarios", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads([line for line in out.splitlines() if line.strip()][-1])
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


def test_endurance_run_emits_convergence_artifacts(tmp_path: Path) -> None:
    payload = run_live_federation_lab(
        tmp_path,
        scenario_name="daemon_endurance_steady_state",
        seed=18,
        node_count=3,
        runtime_s=1.0,
        clean=True,
        runtime_mode="worker",
    )
    run_root = tmp_path / payload["artifact_paths"]["run_root"]
    assert payload["family"] == "endurance"
    assert (run_root / "convergence_summary.json").exists()
    assert (run_root / "final_cluster_state_digest.json").exists()
    assert (run_root / "staged_timeline_report.json").exists()


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
    out = capsys.readouterr().out
    payload = json.loads([line for line in out.splitlines() if line.strip()][-1])
    assert payload["runtime_mode_requested"] == "worker"
    assert payload["runtime_mode_resolved"] == "worker"


def test_ops_endurance_suite_route(tmp_path: Path, capsys) -> None:
    rc = ops_main(["--repo-root", str(tmp_path), "lab", "federation", "--endurance-suite", "--mode", "worker", "--seed", "5", "--json"])
    assert rc in {0, 1}
    out = capsys.readouterr().out
    payload = json.loads([line for line in out.splitlines() if line.strip()][-1])
    assert payload["suite"] == "federation_endurance"
    assert payload["run_count"] >= 1
