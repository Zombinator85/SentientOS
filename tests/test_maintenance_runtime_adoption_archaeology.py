import json
from pathlib import Path
from typing import Any, cast

import pytest


pytestmark = pytest.mark.no_legacy_skip

EVIDENCE = Path("architecture/maintenance_runtime_adoption_chain.json")


def _load() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(EVIDENCE.read_text(encoding="utf-8")))


def test_adoption_archaeology_evidence_is_closed_deterministic_and_non_authoritative() -> None:
    first = EVIDENCE.read_bytes()
    evidence = _load()
    assert evidence["schema"] == "sentientos.maintenance_runtime_adoption_chain:v1"
    assert evidence["authoritative_runtime_behavior"] is False
    assert json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=False).encode() + b"\n" == first
    identities = [stage["stable_identity"] for stage in evidence["stages"]]
    assert len(identities) == len(set(identities))
    assert identities[0] == "maintenance_candidate_proposal"
    assert identities[-1] == "resident_readiness_completion"
    for index, stage in enumerate(evidence["stages"]):
        assert stage["confidence"] in evidence["confidence_ontology"]
        assert stage["previous_stage"] == (identities[index - 1] if index else None)
        assert stage["next_stage"] == (identities[index + 1] if index + 1 < len(identities) else None)
        assert stage["classification"] in {
            "stochastic_advisory", "deterministic_authoritative",
            "mixed_with_defined_authority_boundary", "unknown",
        }


def test_every_referenced_implementation_surface_exists() -> None:
    evidence = _load()
    for stage in evidence["stages"]:
        for reference in stage["implementation"]:
            path_text, symbol = reference.split(":", 1)
            path = Path(path_text)
            assert path.is_file(), reference
            source = path.read_text(encoding="utf-8")
            assert symbol.split(".")[-1] in source, reference


def test_archaeology_artifact_has_no_runtime_consumer() -> None:
    needle = EVIDENCE.as_posix()
    runtime_references = []
    for path in Path("sentientos").rglob("*.py"):
        if needle in path.read_text(encoding="utf-8"):
            runtime_references.append(path.as_posix())
    assert runtime_references == []
