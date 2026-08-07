from __future__ import annotations

from sentientos import maintenance_autonomy_cycle as cycle


def test_explicit_watchdog_status_mapping_never_calls_waiting_complete() -> None:
    assert cycle._map_watchdog({"status": "waiting", "ticks": []}, had_candidate=True) == "autonomy_cycle_waiting"
    assert cycle._map_watchdog({"status": "blocked", "ticks": []}, had_candidate=True) == "autonomy_cycle_blocked"
    assert cycle._map_watchdog({"status": "paused", "ticks": []}, had_candidate=True) == "autonomy_cycle_paused"


def test_completion_requires_close_then_idle() -> None:
    result = {"status": "idle", "ticks": [{"transition": "close_task", "status": "completed"}, {"transition": "idle", "status": "idle"}]}
    assert cycle._map_watchdog(result, had_candidate=True) == "autonomy_cycle_completed"
    assert cycle._map_watchdog({"status": "idle", "ticks": []}, had_candidate=True) == "autonomy_cycle_idle"
