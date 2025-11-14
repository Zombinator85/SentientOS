from datetime import datetime, timezone

from sentientos.cathedral import Amendment
from sentientos.cathedral.invariants import evaluate_invariants


def _make_amendment(changes):
    return Amendment(
        id="test-amend",
        created_at=datetime(2024, 2, 1, 9, 30, tzinfo=timezone.utc),
        proposer="user",
        summary="Routine experiment tuning",
        changes=changes,
        reason="Align schedules",
    )


def test_safe_amendment_passes_invariants():
    amendment = _make_amendment(
        {
            "experiments": {"update": "demo_simple_success"},
            "actions": ["document_change"],
        }
    )
    assert evaluate_invariants(amendment) == []


def test_detects_required_field_removal():
    amendment = _make_amendment({"removed_fields": ["runtime.required_timeout"]})
    violations = evaluate_invariants(amendment)
    assert any("Invariant 1" in v for v in violations)


def test_detects_recursion_risk():
    amendment = _make_amendment(
        {
            "recursion": ["recursive_codex_call"],
            "governance": {"mutates_cathedral": True},
        }
    )
    violations = evaluate_invariants(amendment)
    assert any("Invariant 4" in v for v in violations)
