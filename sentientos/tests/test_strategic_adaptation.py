from __future__ import annotations

import json
from pathlib import Path

from sentientos.goal_graph import Goal, GoalGraph, GoalStateRecord, persist_goal_graph, persist_goal_state
from sentientos.strategic_adaptation import approve_proposal, create_adjustment_proposal


def _seed_goal_graph(root: Path) -> None:
    graph = GoalGraph(
        schema_version=1,
        goals=(
            Goal(
                goal_id="integrity_core",
                description="keep integrity",
                weight=0.7,
                priority=10,
                dependencies=(),
                completion_check="check_integrity_baseline_ok",
                risk_cost_estimate=1,
                throughput_cost_estimate=1,
                tags=("integrity", "integrity_core"),
                enabled=True,
            ),
            Goal(
                goal_id="feature_delivery",
                description="ship features",
                weight=0.6,
                priority=8,
                dependencies=(),
                completion_check="check_forge_last_run_ok",
                risk_cost_estimate=2,
                throughput_cost_estimate=2,
                tags=("feature",),
                enabled=True,
            ),
        ),
    )
    persist_goal_graph(root, graph)
    state = {
        "integrity_core": GoalStateRecord(1, 0.4, "active", None, None, (), None, 0),
        "feature_delivery": GoalStateRecord(1, 0.2, "blocked", None, None, (), "missing_anchor", 2),
    }
    persist_goal_state(root, state)


def _seed_pulse(root: Path) -> None:
    (root / "pulse").mkdir(parents=True, exist_ok=True)
    (root / "pulse/integrity_incidents.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"created_at": "2099-01-01T00:00:00Z", "triggers": ["anchor_mismatch"], "quarantine_activated": True, "path": "glow/forge/incidents/incident_1.json"}, sort_keys=True),
                json.dumps({"created_at": "2099-01-01T03:00:00Z", "triggers": ["anchor_mismatch"], "quarantine_activated": False, "path": "glow/forge/incidents/incident_2.json"}, sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "pulse/orchestrator_ticks.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"generated_at": "2099-01-01T01:00:00Z", "integrity_pressure_level": 2, "remediation_status": "succeeded", "tick_report_path": "glow/forge/orchestrator/ticks/tick_1.json"}, sort_keys=True),
                json.dumps({"generated_at": "2099-01-01T02:00:00Z", "integrity_pressure_level": 2, "remediation_status": "failed", "tick_report_path": "glow/forge/orchestrator/ticks/tick_2.json"}, sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_proposal_generation_is_deterministic_and_bounded(tmp_path: Path) -> None:
    _seed_goal_graph(tmp_path)
    _seed_pulse(tmp_path)

    proposal, path = create_adjustment_proposal(tmp_path)
    again, path2 = create_adjustment_proposal(tmp_path)

    assert proposal.proposal_id == again.proposal_id
    assert path == path2
    assert proposal.schema_version == 2
    assert len(proposal.adjustments) <= proposal.guardrails.max_goals_changed
    assert "allocation_diff" in proposal.predicted_effects[-1]
    assert "added_selected" in proposal.allocation_diff
    assert "selected_goals" in proposal.current_allocation_summary
    assert "selected_goals" in proposal.proposed_allocation_summary
    for item in proposal.adjustments:
        if item.field == "weight":
            assert abs(float(item.new) - float(item.old)) <= proposal.guardrails.max_weight_delta_per_proposal


def test_approval_apply_writes_change_and_updates_goal_graph(tmp_path: Path) -> None:
    _seed_goal_graph(tmp_path)
    _seed_pulse(tmp_path)
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/receipts_index.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "glow/forge/receipts/anchors").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/anchors/anchor_1.json").write_text(json.dumps({"anchor_id": "a1"}) + "\n", encoding="utf-8")

    proposal, rel = create_adjustment_proposal(tmp_path)
    approved, change_id = approve_proposal(
        tmp_path,
        proposal_path=tmp_path / rel,
        approve=True,
        approved_by="manual",
        decision_notes="ok",
        apply=True,
        enforce_stable=False,
    )

    assert approved.approval.status == "approved"
    assert change_id is not None
    rows = (tmp_path / "pulse/strategic_changes.jsonl").read_text(encoding="utf-8").splitlines()
    assert rows
    payload = json.loads(rows[-1])
    assert payload["change_id"] == change_id


def test_auto_apply_prevented_when_unstable(tmp_path: Path) -> None:
    _seed_goal_graph(tmp_path)
    _seed_pulse(tmp_path)
    (tmp_path / "glow/forge/pressure_state.json").write_text(json.dumps({"schema_version": 1, "level": 3}) + "\n", encoding="utf-8")
    (tmp_path / "glow/forge/quarantine.json").write_text(json.dumps({"schema_version": 1, "active": True}) + "\n", encoding="utf-8")

    _, rel = create_adjustment_proposal(tmp_path)
    approved, change_id = approve_proposal(
        tmp_path,
        proposal_path=tmp_path / rel,
        approve=True,
        approved_by="policy",
        decision_notes="try auto",
        apply=True,
        enforce_stable=True,
    )

    assert approved.approval.status == "approved"
    assert change_id is None
