from pathlib import Path

from sentientos.ethics.consent_memory_vault import ConsentMemoryVault
from sentientos.meta.ambiguity_resolver import AmbiguityResolver


def test_ambiguity_resolver_emits_requests_and_resolutions(tmp_path: Path):
    vault = ConsentMemoryVault(tmp_path / "consent_log.jsonl")
    vault.log_consent("simulation", status="denied", context="do not simulate affect")

    instructions = [
        {"task": "simulate mood", "capability": "simulation", "ambiguity": "ethical"},
        {"task": "summarize log", "guardrails": {"tone": "neutral"}},
    ]
    dialogue_history = [
        {"id": "d1", "topic": "summarize log", "notes": "keep brief"},
    ]

    resolver = AmbiguityResolver(tmp_path, consent_vault=vault)
    result = resolver.run(instructions, dialogue_history=dialogue_history, glow_fragments=[{"hint": "prior denial"}])

    clarification_path = tmp_path / "clarification_request.jsonl"
    resolution_path = tmp_path / "autonomous_resolution.jsonl"

    assert clarification_path.exists()
    assert resolution_path.exists()

    clarifications = clarification_path.read_text(encoding="utf-8").strip().splitlines()
    resolutions = resolution_path.read_text(encoding="utf-8").strip().splitlines()

    assert any("consent_conflict" in line for line in resolutions)
    assert any("missing_guardrails" in line or "ambiguity" in line for line in clarifications)

    # Disambiguation examples with precedent trace
    assert "consent:simulation:denied" in resolutions[0]
    assert "dialogue" in resolutions[-1] or "dialogue" in clarifications[-1]
