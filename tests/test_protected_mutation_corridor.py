from __future__ import annotations

from sentientos.protected_mutation_corridor import (
    classify_touched_paths,
    corridor_definition,
    is_corridor_artifact_class,
    is_corridor_path,
)


def test_touched_path_inside_corridor_is_relevant() -> None:
    payload = classify_touched_paths(["vow/immutable_manifest.json"])
    assert payload["intersects_corridor"] is True
    assert payload["implicated_domains"] == ["immutable_manifest_identity_writes"]


def test_touched_path_outside_corridor_is_not_applicable() -> None:
    payload = classify_touched_paths(["README.md"])
    assert payload["intersects_corridor"] is False
    assert payload["implicated_domains"] == []


def test_mixed_touched_paths_report_implicated_domains() -> None:
    payload = classify_touched_paths([
        "README.md",
        "vow/immutable_manifest.json",
        "glow/forge/recovery_ledger.jsonl",
    ])
    assert payload["intersects_corridor"] is True
    assert payload["implicated_domains"] == [
        "codexhealer_repair_regenesis_linkage",
        "immutable_manifest_identity_writes",
    ]


def test_machine_readable_definition_is_stable_shape() -> None:
    definition = corridor_definition()
    assert definition["scope_id"] == "protected_mutation_proof:v1:covered_corridor"
    assert isinstance(definition["domains"], list)
    assert all("path_globs" in domain for domain in definition["domains"])


def test_corridor_path_and_artifact_class_helpers() -> None:
    assert is_corridor_path("pulse/forge_events.jsonl") is True
    assert is_corridor_path("docs/random.md") is False
    assert is_corridor_artifact_class("immutable_manifest") is True
    assert is_corridor_artifact_class("uncovered_artifact") is False
