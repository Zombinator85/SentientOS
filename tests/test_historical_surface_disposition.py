from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from sentientos.historical_surface_disposition import (
    InventoryReport,
    SCHEMA,
    build_inventory_report,
    dumps_report,
    load_registry,
    parse_registry,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "architecture" / "historical_surface_dispositions.json"
COUNCIL_LINEAGES = ROOT / "architecture" / "council_lineages.json"


def payload(*records: dict[str, object], scope: list[str] | None = None) -> dict[str, object]:
    return {"schema": SCHEMA, "inventory_scope": scope or ["present.py"], "records": list(records)}


def record(
    surface_id: str = "surface",
    *,
    paths: list[str] | None = None,
    disposition: str = "canonical",
    successor: str | None = None,
) -> dict[str, object]:
    return {
        "id": surface_id,
        "paths": paths or ["present.py"],
        "disposition": disposition,
        "rationale": "test evidence",
        "owner": "test",
        "successor": successor,
        "references": ["evidence.md"],
    }


def report_for(tmp_path: Path, raw: dict[str, object]) -> InventoryReport:
    (tmp_path / "present.py").write_text("raise RuntimeError('must not execute')\n", encoding="utf-8")
    registry, errors = parse_registry(raw)
    return build_inventory_report(registry, tmp_path, errors)


def test_seed_registry_validates_and_preserves_bounded_claims() -> None:
    registry, errors = load_registry(REGISTRY)
    report = build_inventory_report(registry, ROOT, errors)
    assert report.valid, report.errors
    by_id = {item.surface_id: item for item in registry.records}
    assert by_id["sentientos-runtime-core"].disposition == "canonical"
    assert by_id["mesh-runtime"].disposition == "alternate_runtime"
    assert by_id["legacy-dialogue-council"].disposition == "unknown_disposition"
    assert report.unclassified_surfaces == ()


def test_invalid_disposition_and_duplicate_ids_fail_deterministically(tmp_path: Path) -> None:
    raw = payload(record(disposition="alive"), record(paths=["other.py"]))
    first = report_for(tmp_path, raw)
    second = report_for(tmp_path, raw)
    assert first == second
    assert any(item.startswith("invalid_disposition:") for item in first.errors)
    assert "duplicate_id:surface" in first.errors


def test_overlapping_classifications_fail(tmp_path: Path) -> None:
    (tmp_path / "tree").mkdir()
    (tmp_path / "tree" / "child.py").write_text("", encoding="utf-8")
    raw = payload(
        record("parent", paths=["tree"]),
        record("child", paths=["tree/child.py"]),
        scope=["tree", "tree/child.py"],
    )
    result = report_for(tmp_path, raw)
    assert any(item.startswith("overlapping_classification:") for item in result.errors)


def test_supersession_requires_resolved_acyclic_successor(tmp_path: Path) -> None:
    required = report_for(tmp_path, payload(record(disposition="superseded")))
    assert "successor_required:surface" in required.errors

    missing = report_for(tmp_path, payload(record(disposition="superseded", successor="absent")))
    assert "missing_successor:surface:absent" in missing.errors

    cyclic = report_for(
        tmp_path,
        payload(
            record("old-a", paths=["present.py"], disposition="superseded", successor="old-b"),
            record("old-b", paths=["other.py"], disposition="superseded", successor="old-a"),
            scope=["present.py", "other.py"],
        ),
    )
    assert any(item.startswith("successor_cycle:") for item in cyclic.errors)


def test_missing_stale_unknown_and_unclassified_are_explicit(tmp_path: Path) -> None:
    raw = payload(
        record("unknown", paths=["missing.py"], disposition="unknown_disposition"),
        scope=["present.py"],
    )
    result = report_for(tmp_path, raw)
    assert result.unknown_surfaces == ("missing.py",)
    assert result.unclassified_surfaces == ("present.py",)
    assert result.missing_targets == ("missing.py",)
    assert result.stale_targets == ("missing.py",)
    assert not any("retired" in value or "superseded" in value for value in result.unknown_surfaces)


def test_report_bytes_are_stable_and_targets_are_never_imported(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    target = tmp_path / "historical.py"
    target.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n", encoding="utf-8")
    raw = payload(record(paths=["historical.py"], disposition="historical_experiment"), scope=["historical.py"])
    registry, errors = parse_registry(raw)
    one = dumps_report(build_inventory_report(registry, tmp_path, errors))
    two = dumps_report(build_inventory_report(registry, tmp_path, errors))
    assert one == two
    assert not marker.exists()


def test_cli_output_is_deterministic() -> None:
    command = [sys.executable, "scripts/report_historical_surface_dispositions.py"]
    first = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    second = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["authority_posture"] == "descriptive_evidence_only"


def test_registry_has_no_authority_fields_or_authority_module_dependencies() -> None:
    raw = REGISTRY.read_text(encoding="utf-8")
    source = (ROOT / "sentientos" / "historical_surface_disposition.py").read_text(encoding="utf-8")
    assert "confers_authority" not in raw
    assert "capability_registry" not in source
    assert "control_plane_kernel" not in source
    assert "runtime_governor" not in source
    # Current admission implementations remain independent of this descriptive module.
    for path in (
        "sentientos/capability_registry.py",
        "sentientos/control_plane_kernel.py",
        "sentientos/runtime_governor.py",
    ):
        assert "historical_surface_disposition" not in (ROOT / path).read_text(encoding="utf-8")


def test_council_lineage_evidence_is_bounded_and_matches_registry() -> None:
    evidence = json.loads(COUNCIL_LINEAGES.read_text(encoding="utf-8"))
    assert evidence["schema"] == "sentientos.council_lineages:v1"
    assert evidence["confidence_ontology"] == [
        "verified_fact",
        "strong_inference",
        "weak_hypothesis",
        "unknown",
    ]
    assert "not one evidenced successor chain" in evidence["non_conflation_conclusion"]["detail"]

    lineages = {item["stable_identity"]: item for item in evidence["surfaces"]}
    assert set(lineages) == {
        "legacy-dialogue-council",
        "mesh-runtime-voices",
        "sentientos-governance-council",
    }
    assert lineages["legacy-dialogue-council"]["disposition"] == "unknown_disposition"
    assert lineages["mesh-runtime-voices"]["disposition"] == "alternate_runtime"
    assert lineages["sentientos-governance-council"]["disposition"] == "canonical"
    assert all(item["predecessor"] is None and item["successor"] is None for item in lineages.values())

    registry, errors = load_registry(REGISTRY)
    assert errors == ()
    dispositions = {item.surface_id: item.disposition for item in registry.records}
    assert dispositions["legacy-dialogue-council"] == lineages["legacy-dialogue-council"]["disposition"]
    assert dispositions["mesh-runtime"] == lineages["mesh-runtime-voices"]["disposition"]
    assert dispositions["sentientos-governance-council"] == lineages["sentientos-governance-council"]["disposition"]


def test_council_archaeology_metadata_cannot_enter_runtime_authority() -> None:
    runtime_authority_paths = (
        "sentientos/capability_registry.py",
        "sentientos/control_plane_kernel.py",
        "sentientos/runtime_governor.py",
        "sentientos/council/governance_council.py",
        "sentient_mesh.py",
    )
    for path in runtime_authority_paths:
        source = (ROOT / path).read_text(encoding="utf-8")
        assert "council_lineages.json" not in source
        assert "historical_surface_dispositions.json" not in source
