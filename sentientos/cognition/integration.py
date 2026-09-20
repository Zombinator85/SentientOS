"""Canonical cognitive-cycle integration API."""
from sentientos.consciousness.integration import (
    cycle_gate_status, daemon_heartbeat, get_current_narrative_goal,
    get_version_consensus_summary, integrity_summary, load_attention_arbitrator,
    load_goal_selection_kernel, load_simulation_engine, run_cognitive_cycle,
)
__all__ = ["cycle_gate_status", "daemon_heartbeat", "get_current_narrative_goal",
           "get_version_consensus_summary", "integrity_summary", "load_attention_arbitrator",
           "load_goal_selection_kernel", "load_simulation_engine", "run_cognitive_cycle"]
