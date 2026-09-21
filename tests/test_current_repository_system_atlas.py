from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from sentientos.capability_registry import build_default_capability_registry

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).resolve().parents[1]
ATLAS_PATH = ROOT / "architecture/current_repository_system_atlas.json"
EVIDENCE_SNAPSHOTS = (
    "architecture/current_repository_system_atlas.json",
    "docs/architecture/current_repository_system_atlas.md",
)
REQUIRED_SECTIONS = {
    "schema_version",
    "repository_sha",
    "generated_at",
    "repository_census",
    "supported_entrypoints",
    "subsystem_records",
    "capability_crosswalk",
    "runtime_composition_records",
    "persistence_records",
    "authority_effect_chains",
    "automatic_background_loops",
    "real_effect_inventory",
    "interfaces",
    "platform_support",
    "legacy_compatibility_families",
    "known_gaps",
    "public_doc_claim_findings",
    "evidence_references",
}


def _atlas() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(ATLAS_PATH.read_text(encoding="utf-8")))


def _records_with_paths(value: Any) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        record_id = str(value.get("id", value.get("capability_id", "record")))
        for key in ("source_paths", "test_paths", "documentation_paths", "evidence_references"):
            paths = value.get(key, ())
            if isinstance(paths, list):
                found.extend((record_id, str(path)) for path in paths)
        for nested in value.values():
            found.extend(_records_with_paths(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_records_with_paths(nested))
    return found


def test_atlas_schema_sha_and_required_sections() -> None:
    atlas = _atlas()
    assert atlas.keys() >= REQUIRED_SECTIONS
    assert atlas["schema_version"] == "current-repository-system-atlas.v1"
    assert re.fullmatch(r"[0-9a-f]{40}", atlas["repository_sha"])
    assert atlas["generated_at"].endswith("Z")


def test_every_registry_capability_is_crosswalked_exactly_once() -> None:
    atlas_ids = [row["capability_id"] for row in _atlas()["capability_crosswalk"]]
    registry_ids = [row.capability_id for row in build_default_capability_registry().records]
    assert Counter(atlas_ids) == Counter(registry_ids)
    assert all(count == 1 for count in Counter(atlas_ids).values())


def test_claimed_evidence_paths_exist_and_have_expected_kinds() -> None:
    atlas = _atlas()
    for record_id, relative in _records_with_paths(atlas):
        path = ROOT / relative
        assert path.exists(), f"{record_id} claims missing evidence path {relative}"
    for row in atlas["subsystem_records"]:
        assert all(path.startswith("tests/") for path in row["test_paths"])
        assert all(path.endswith(".md") for path in row["documentation_paths"])


def test_surface_classifications_use_declared_independent_vocabularies() -> None:
    atlas = _atlas()
    vocab = atlas["classification_vocabularies"]
    field_to_vocab = {
        "implementation_maturity": "implementation_maturity",
        "runtime_liveness": "runtime_liveness",
        "effect_posture": "effect_posture",
        "authority_posture": "authority_posture",
        "activation_posture": "activation_posture",
        "persistence_posture": "persistence_posture",
    }
    for row in atlas["subsystem_records"]:
        for field, vocabulary in field_to_vocab.items():
            assert row[field] in vocab[vocabulary], (row["id"], field, row[field])


def test_effect_and_resident_claims_carry_composition_evidence() -> None:
    for row in _atlas()["subsystem_records"]:
        if row["effect_posture"] == "bounded_real_effect":
            assert row["source_paths"], row["id"]
        if row["runtime_liveness"] == "resident_composed":
            assert row["current_entrypoints"], row["id"]
            assert any(path == "sentientosd.py" for path in row["source_paths"]), row["id"]


def test_nonproduction_maturity_cannot_be_default_production_active() -> None:
    for row in _atlas()["subsystem_records"]:
        if row["implementation_maturity"] in {"test_only", "synthetic_only"} or row["runtime_liveness"] == "test_only":
            assert row["activation_posture"] != "default active", row["id"]
            assert row["production_effect_reachable"] is False, row["id"]


def test_legacy_family_inventory_covers_each_tracked_path_once() -> None:
    atlas = _atlas()
    inventoried = [path for family in atlas["legacy_compatibility_families"] for path in family["members"]]
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout.splitlines()
    # The atlas and its new test/docs are task-owned additions and were not tracked at the
    # recorded SHA; all paths that existed at that SHA must nevertheless be covered exactly once.
    recorded = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", atlas["repository_sha"]],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    assert Counter(inventoried) == Counter(recorded)
    assert set(recorded) <= set(tracked)


def test_atlas_evidence_snapshots_are_not_rewritten_with_forward_docs() -> None:
    for relative in EVIDENCE_SNAPSHOTS:
        recorded = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert (ROOT / relative).read_bytes() == recorded, relative
