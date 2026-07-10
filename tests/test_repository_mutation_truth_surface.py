from __future__ import annotations

from pathlib import Path

from sentientos.capability_registry import build_default_capability_registry


def test_docs_no_default_autonomous_commit_push_claims() -> None:
    for name in ["README.md", "docs/architecture/public_technical_overview.md"]:
        text = Path(name).read_text(encoding="utf-8").lower()
        assert "repository mutation custody" in text
        assert "does not stage files" in text
        assert "does not stage files, create commits" in text


def test_capability_registry_marks_repository_mutation_posture() -> None:
    records = build_default_capability_registry().by_id()
    handoff = records["repository_mutation_handoff"]
    blocked = records["autonomous_repository_stage_commit_push"]
    assert handoff.status == "implemented"
    assert handoff.authority_level in {"metadata_verification_only", "review_only"}
    assert blocked.status in {"blocked", "deferred"}
    assert handoff.network_required is False
    assert handoff.provider_required is False
    assert handoff.prompt_assembly_required is False
    assert handoff.host_actuation_performed is False
