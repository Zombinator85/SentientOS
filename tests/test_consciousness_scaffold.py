from __future__ import annotations

from pathlib import Path

from attention_arbitrator import AttentionArbitrator, PulseEvent
from inner_narrator import InnerNarrator
from sentience_kernel import SentienceKernel
from simulation_engine import SimulationEngine


def test_attention_arbitrator_prefers_priority_then_relevance():
    arbitrator = AttentionArbitrator()
    low = PulseEvent(payload={"topic": "low"}, priority="low", relevance=0.9, timestamp=1.0)
    high = PulseEvent(payload={"topic": "high"}, priority="high", relevance=0.6, timestamp=2.0)
    higher_relevance = PulseEvent(payload={"topic": "relevant"}, priority="high", relevance=0.95, timestamp=3.0)

    for event in (low, high, higher_relevance):
        arbitrator.submit(event)

    winner = arbitrator.choose_focus()
    assert winner is higher_relevance  # higher relevance should break ties within the same priority
    snapshot = arbitrator.focus_snapshot()
    assert snapshot["priority"] == "high"
    assert snapshot["source"] == higher_relevance.origin
    context = arbitrator.context_window(limit=2)
    assert len(context["summary"]) == 2


def test_sentience_kernel_blocks_forbidden_goals():
    kernel = SentienceKernel()
    blocked = kernel.generate_proposal(preferred_goal="alter_vow")
    assert blocked is None
    allowed = kernel.generate_proposal(preferred_goal="reflect_and_prepare")
    assert allowed is not None
    assert kernel.last_proposal() is allowed


def test_inner_narrator_records_and_persists(tmp_path: Path):
    narrator = InnerNarrator()
    narrator.reflect("cycle complete", mood="curious", confidence=0.7, focus="focus_a", tags=["introspection"])
    latest = narrator.latest()
    assert latest is not None
    assert latest.summary == "cycle complete"

    output = tmp_path / "glow" / "introspection.jsonl"
    narrator.persist(output)
    assert output.exists()
    assert output.read_text().strip() != ""


def test_simulation_engine_scales_confidence_with_participants():
    engine = SimulationEngine()
    result_one = engine.run("sim_single", "test", participants=["a"])
    result_three = engine.run("sim_multi", "test", participants=["a", "b", "c"])
    assert result_three.confidence > result_one.confidence
    assert engine.last_result() is result_three
