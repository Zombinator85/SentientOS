import pytest

from sentientos.emergence_idle_state import EmergenceIdleState


pytestmark = pytest.mark.no_legacy_skip


def test_emergence_idle_state_marks_idle_and_exit_conditions():
    idle_state = EmergenceIdleState(soft_threshold=0.2)

    idle_snapshot = idle_state.evaluate(active_governance=[], reflex_anomalies=[], symbolic_drift=0.1)

    assert idle_snapshot["idle"] is True
    assert idle_snapshot["snapshot"].governance_polling is False
    assert idle_snapshot["snapshot"].reflection_mode == "summary"
    assert "Symbolic drift exceeds" in idle_snapshot["markdown"]

    exit_snapshot = idle_state.evaluate(
        active_governance=[{"proposal_id": "p1"}],
        reflex_anomalies=[{"anomaly": "spike"}],
        symbolic_drift=0.3,
    )

    assert exit_snapshot["idle"] is False
    assert exit_snapshot["snapshot"].pruner_status == "tracking"
    assert "Idle suspended" in exit_snapshot["snapshot"].summary
