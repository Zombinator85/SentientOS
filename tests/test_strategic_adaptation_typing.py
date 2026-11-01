import json

import pytest

from sentientos.strategic_adaptation import _load_proposal


def test_load_proposal_preserves_nested_json_record_types(tmp_path):
    path = tmp_path / "proposal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "proposal_id": "proposal-1",
                "created_at": "2026-11-01T00:00:00Z",
                "base_goal_graph_hash": "graph-digest",
                "window": {"name": "last_24h", "start": "start", "end": "end"},
                "inputs_summary": {"pressure_level_distribution": {"2": 2}},
                "adjustments": [
                    {
                        "goal_id": "goal-1",
                        "field": "priority",
                        "old": 3,
                        "new": 2,
                        "reason": "repeated_block",
                        "evidence_paths": ["pulse/tick.jsonl"],
                    }
                ],
                "adjustment_refusals": [{"goal_id": "goal-2", "field": "weight", "reason": "protected"}],
                "allocator_inputs_snapshot": {"pressure_level": 2},
                "current_allocation_summary": {"selected_goals": ["goal-1"]},
                "proposed_allocation_summary": {"selected_goals": ["goal-1"]},
                "allocation_diff": {"added_selected": [], "removed_selected": []},
                "predicted_effects": ["hold_graph_constant"],
                "guardrails": {"max_weight_delta_per_proposal": 0.2, "max_goals_changed": 5, "forbidden_tags": ["integrity_core"]},
                "approval": {"status": "proposed", "approved_by": None, "decision_notes": ""},
            }
        ),
        encoding="utf-8",
    )

    proposal = _load_proposal(path)

    assert proposal.adjustments[0].goal_id == "goal-1"
    assert proposal.adjustments[0].evidence_paths == ("pulse/tick.jsonl",)
    assert proposal.adjustment_refusals == ({"goal_id": "goal-2", "field": "weight", "reason": "protected"},)
    assert proposal.inputs_summary == {"pressure_level_distribution": {"2": 2}}
    assert proposal.guardrails.max_goals_changed == 5


def test_load_proposal_rejects_non_numeric_guardrails(tmp_path):
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps({"guardrails": {"max_goals_changed": "many"}}), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid_strategic_integer"):
        _load_proposal(path)
