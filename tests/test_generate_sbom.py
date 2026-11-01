from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import generate_sbom

pytestmark = pytest.mark.no_legacy_skip


def test_sbom_component_sources_serialize_to_cyclonedx(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / "Cargo.lock"
    lock_path.write_text('[[package]]\nname = "sentientos-core"\nversion = "1.2.3"\n', encoding="utf-8")
    monkeypatch.setattr(generate_sbom, "get_data_root", lambda: tmp_path)

    python_components = generate_sbom._requirements_components(["numpy==2.1", "# ignored", "orjson"])
    rust_components = generate_sbom._cargo_components(lock_path)
    generate_sbom._write_bom("combined.json", [*python_components, *rust_components])

    payload = json.loads((tmp_path / "glow" / "provenance" / "combined.json").read_text(encoding="utf-8"))
    assert payload["bomFormat"] == "CycloneDX"
    assert payload["components"] == [
        {"type": "library", "name": "numpy", "version": "2.1"},
        {"type": "library", "name": "orjson", "version": "latest"},
        {"type": "library", "name": "sentientos-core", "version": "1.2.3"},
    ]
