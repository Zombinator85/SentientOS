import pytest

from sentientos.orchestrator import SentientOrchestrator


pytestmark = pytest.mark.no_legacy_skip


def test_orchestrator_without_profile_errors():
    orchestrator = SentientOrchestrator()

    assert orchestrator.ssa_dry_run()["error"] == "no_profile_loaded"
    assert orchestrator.ssa_execute(relay=None)["error"] == "no_profile_loaded"
    assert orchestrator.ssa_prefill_827()["error"] == "no_profile_loaded"


def test_orchestrator_with_profile_returns_dry_run_plan():
    orchestrator = SentientOrchestrator(profile={"first_name": "Test"})

    plan = orchestrator.ssa_dry_run()

    assert plan["status"] == "dry_run_plan_ready"
    assert plan["pages"]


def test_orchestrator_enforces_approval_gate():
    orchestrator = SentientOrchestrator(profile={"first_name": "Test"}, approval=False)

    prefill = orchestrator.ssa_prefill_827()

    assert prefill["status"] == "approval_required"

