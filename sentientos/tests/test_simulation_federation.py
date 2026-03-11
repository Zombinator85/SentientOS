from __future__ import annotations

import json
from pathlib import Path

from sentientos.ops import main as ops_main
from sentientos.simulation.federation import (
    load_federation_baseline_manifest,
    run_federation_baseline_suite,
    run_federation_simulation,
)


def test_simulation_reproducible(tmp_path: Path) -> None:
    one = run_federation_simulation(tmp_path, scenario_name="healthy_3node", seed=13)
    two = run_federation_simulation(tmp_path, scenario_name="healthy_3node", seed=13)
    assert one["quorum"] == two["quorum"]
    assert one["oracle"] == two["oracle"]


def test_quorum_failure_oracle(tmp_path: Path) -> None:
    payload = run_federation_simulation(tmp_path, scenario_name="quorum_failure", seed=11)
    assert payload["oracle"]["passed"] is True
    assert payload["quorum"]["admit"] is False


def test_replay_storm_duplicates_are_bounded(tmp_path: Path) -> None:
    payload = run_federation_simulation(tmp_path, scenario_name="replay_storm", seed=5)
    assert payload["oracle"]["observed"]["duplicate_events"] == 12


def test_ops_simulate_cli_json(tmp_path: Path, capsys) -> None:
    rc = ops_main(["--repo-root", str(tmp_path), "simulate", "federation", "--scenario", "healthy_3node", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sentientos.ops"
    assert payload["command"] == "simulate.federation"


def test_ops_simulate_list_scenarios(tmp_path: Path, capsys) -> None:
    rc = ops_main(["--repo-root", str(tmp_path), "simulate", "federation", "--list-scenarios", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    names = {row["name"] for row in payload["scenarios"]}
    assert "healthy_3node" in names


def test_baseline_suite_reproducible(tmp_path: Path) -> None:
    first = run_federation_baseline_suite(tmp_path)
    second = run_federation_baseline_suite(tmp_path)
    assert first["status"] == "passed"
    assert first["scenarios"] == second["scenarios"]


def test_baseline_gate_cli_exit_code_success(tmp_path: Path, capsys) -> None:
    rc = ops_main(["--repo-root", str(tmp_path), "simulate", "federation", "--baseline", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["report_path"] == "glow/simulation/baseline_report.json"


def test_baseline_gate_cli_exit_code_failure(tmp_path: Path, capsys, monkeypatch) -> None:
    from sentientos.simulation import federation as sim_federation

    manifest = load_federation_baseline_manifest()
    manifest["scenarios"][0]["expected_oracle"] = {"quorum_admit": False}
    override_manifest = tmp_path / "override_manifest.json"
    override_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(sim_federation, "BASELINE_MANIFEST_PATH", override_manifest)

    rc = ops_main(["--repo-root", str(tmp_path), "simulate", "federation", "--baseline", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["status"] == "failed"
    assert "healthy_3node" in payload["gating_failures"]


def test_baseline_manifest_inclusion_policy() -> None:
    manifest = load_federation_baseline_manifest()
    names = [row["name"] for row in manifest["scenarios"]]
    assert names == [
        "healthy_3node",
        "quorum_failure",
        "replay_storm",
        "reanchor_continuation",
        "pressure_local_safety",
    ]
    assert all(bool(row["release_gating"]) for row in manifest["scenarios"])


def test_baseline_report_is_deterministic(tmp_path: Path) -> None:
    run_federation_baseline_suite(tmp_path)
    first = (tmp_path / "glow/simulation/baseline_report.json").read_text(encoding="utf-8")
    run_federation_baseline_suite(tmp_path)
    second = (tmp_path / "glow/simulation/baseline_report.json").read_text(encoding="utf-8")
    assert first == second
