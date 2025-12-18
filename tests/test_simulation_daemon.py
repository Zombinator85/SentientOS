import json
from pathlib import Path

from sentientos.simulation import SimulationDaemon


def test_simulation_daemon_generates_result_file(tmp_path):
    daemon = SimulationDaemon(tmp_path)
    base_state = {
        "ledger": {"credits": 10, "debts": 2},
        "emotion_state": {"calm": 0.7},
    }
    proposal = {
        "ledger": {"credits": 2, "debts": -1},
        "emotion_state": {"calm": -0.2, "anticipation": 0.3},
        "symbolic": ["ritual"],
    }

    result = daemon.simulate(proposal, base_state=base_state)

    assert Path(result["result_path"]).exists()
    assert result["ledger_delta"] == {"credits": 2, "debts": -1}
    assert result["emotion_delta"]["calm"] == -0.2

    saved = json.loads(Path(result["result_path"]).read_text())
    assert saved["symbolic_impact"]["symbolic_terms"] == ["ritual"]
    assert saved["volatility"]["composite"] > 0
