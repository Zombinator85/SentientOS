from __future__ import annotations

import json
from pathlib import Path

from sentientos.ops import main as ops_main
from sentientos.simulation.federation import run_federation_simulation


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
