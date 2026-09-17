import json
from pathlib import Path
from typing import Any, cast

import pytest


pytestmark = pytest.mark.no_legacy_skip

EVIDENCE = Path("architecture/authoritative_state_evidence_custody.json")


def _load() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(EVIDENCE.read_text(encoding="utf-8")))


def test_state_evidence_archaeology_is_deterministic_and_non_authoritative() -> None:
    raw = EVIDENCE.read_bytes()
    evidence = _load()
    assert evidence["schema"] == "sentientos.authoritative_state_evidence_custody:v1"
    assert evidence["authoritative_runtime_behavior"] is False
    assert evidence["generated"] is False
    assert json.dumps(evidence, indent=2, ensure_ascii=False).encode() + b"\n" == raw
    identities = [surface["identity"] for surface in evidence["surfaces"]]
    assert len(identities) == len(set(identities))
    assert {surface["confidence"] for surface in evidence["surfaces"]} <= set(evidence["confidence_ontology"])


def test_every_referenced_state_surface_and_symbol_exists() -> None:
    for surface in _load()["surfaces"]:
        for reference in surface["implementation"]:
            path_text, symbol = reference.split(":", 1)
            path = Path(path_text)
            assert path.is_file(), reference
            assert symbol.split(".")[-1] in path.read_text(encoding="utf-8"), reference


def test_archaeology_metadata_has_no_runtime_consumer() -> None:
    needle = EVIDENCE.as_posix()
    consumers = [
        path.as_posix()
        for path in Path("sentientos").rglob("*.py")
        if needle in path.read_text(encoding="utf-8")
    ]
    assert consumers == []
