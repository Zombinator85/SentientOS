from __future__ import annotations

from pathlib import Path

from sentientos.meta.narrative_genealogy import NarrativeGenealogy


def test_narrative_genealogy_builds_chain(tmp_path: Path):
    workspace = tmp_path / "meta"
    genealogy = NarrativeGenealogy(workspace)

    artifact = workspace / "digests/2025-12-11.md"
    record = genealogy.trace_artifact(
        artifact,
        daemon="ReflectionLoop",
        reflex={"source": "CodexDaemon", "type": "patch_summary"},
        precedent={"source": "user", "type": "request", "id": "session-4fa9"},
    )

    assert record["artifact"].endswith("2025-12-11.md")
    assert any(entry["type"] == "patch_summary" for entry in record["origin_chain"])

    stored = genealogy.load_genealogy()
    assert stored, "genealogy_chain.jsonl should contain the traced artifact"
    assert stored[0]["origin_chain"][0]["source"] == "ReflectionLoop"
