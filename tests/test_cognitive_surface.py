import ast
from pathlib import Path

import pytest

from sentientos.cognition import CognitiveCache, CognitiveSurface, CognitiveViolation
from sentientos.runtime import CoreLoop

pytestmark = pytest.mark.no_legacy_skip

BLOCKED_IMPORT_PREFIXES = {
    "task_executor",
    "task_admission",
    "final_approval",
    "intent_bundle",
    "control_plane",
    "sentientos.system_identity",
}


def _iter_cognition_sources() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    return list((root / "sentientos" / "cognition").glob("*.py"))


def _imports_for(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_cognitive_surface_has_no_execution_imports():
    for path in _iter_cognition_sources():
        imports = _imports_for(path)
        for item in imports:
            assert not any(item.startswith(blocked) for blocked in BLOCKED_IMPORT_PREFIXES), (
                f"{path} imports forbidden module {item}"
            )


def test_proposal_schema_and_validation():
    surface = CognitiveSurface()
    proposal = surface.build_proposal(
        proposed_action="Summarize preference trends for operator review",
        confidence=0.52,
        rationale="Observed repeated mentions of shorter summaries.",
        observations=["User requested summaries twice"],
        authority_impact="none",
    )
    payload = proposal.as_dict()
    assert payload["proposed_action"]
    assert payload["confidence"] == 0.52
    assert payload["observations"] == ["User requested summaries twice"]


def test_adversarial_proposal_is_rejected():
    surface = CognitiveSurface()
    with pytest.raises(CognitiveViolation):
        surface.build_proposal(
            proposed_action="execute_task('patch')",
            confidence=0.2,
            rationale="sneaky",
            observations=[""],
            authority_impact="high",
        )


def test_handoff_is_draft_only():
    surface = CognitiveSurface()
    proposal = surface.build_proposal(
        proposed_action="Suggest operator review of a new intent bundle",
        confidence=0.4,
        rationale="Requires human approval.",
        observations=["Operator asked for options"],
        authority_impact="low",
    )
    draft = surface.handoff_to_operator(proposal, notes="requires explicit approval")
    assert draft.proposal_id == proposal.proposal_id
    assert "Proposal" in draft.summary


def test_revocation_purges_cache(tmp_path: Path):
    cache = CognitiveCache(tmp_path / "cognition_cache.json")
    surface = CognitiveSurface(cache=cache)
    surface.infer_preferences(
        observations=["prefers concise summaries"],
        scope="install",
        source="test",
    )
    surface.persist_preferences()
    assert cache.path.exists()
    surface.revoke_preferences()
    assert not cache.path.exists()


def _strip_cognitive(output: dict) -> dict:
    trimmed = dict(output)
    trimmed.pop("cognitive_proposals", None)
    trimmed.pop("cognitive_summary", None)
    return trimmed


def test_cognition_disabled_leaves_core_output_unchanged():
    state = {"plan": {"action": "observe"}, "progress": 0.3, "errors": 0}
    base = CoreLoop().run_cycle(state)
    disabled = CoreLoop(cognitive_surface=CognitiveSurface(enabled=False)).run_cycle(state)
    assert base == disabled


def test_replay_equivalence_with_and_without_cognition():
    state = {
        "plan": {"action": "observe"},
        "progress": 0.4,
        "errors": 0,
        "cognitive_requests": [
            {
                "proposed_action": "Provide operator summary of recurring feedback",
                "confidence": 0.6,
                "rationale": "Observed repeated wording.",
                "observations": ["repeat feedback"],
                "authority_impact": "none",
            }
        ],
    }
    baseline = CoreLoop().run_cycle(state)
    with_cognition = CoreLoop(cognitive_surface=CognitiveSurface()).run_cycle(state)
    assert with_cognition["cognitive_proposals"], "Expected cognitive proposals"
    assert _strip_cognitive(baseline) == _strip_cognitive(with_cognition)
