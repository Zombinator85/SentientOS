#!/usr/bin/env python3
"""Generate lightweight CycloneDX SBOMs for SentientOS."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from sentientos.storage import get_data_root


def _requirements_components(requirements: Iterable[str]) -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    for line in requirements:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, version = line.partition("==")
        components.append({
            "type": "library",
            "name": name,
            "version": version or "latest",
        })
    return components


def _cargo_components(lock_path: Path) -> list[dict[str, object]]:
    if not lock_path.exists():
        return []
    components: list[dict[str, object]] = []
    package = None
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("[[package]]"):
            if package:
                components.append(package)
            package = {"type": "library"}
        elif line.startswith("name =") and package is not None:
            package["name"] = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("version =") and package is not None:
            package["version"] = line.split("=", 1)[1].strip().strip('"')
    if package:
        components.append(package)
    return components


def _write_bom(name: str, components: list[dict[str, object]]) -> None:
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"name": "SentientOS"}},
        "components": components,
    }
    output = get_data_root() / "glow" / "provenance"
    output.mkdir(parents=True, exist_ok=True)
    path = output / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    requirements_path = Path("requirements.txt")
    if requirements_path.exists():
        components = _requirements_components(requirements_path.read_text(encoding="utf-8").splitlines())
        _write_bom("python-sbom.json", components)
    cargo_lock = Path("Cargo.lock")
    if cargo_lock.exists():
        components = _cargo_components(cargo_lock)
        _write_bom("rust-sbom.json", components)
    images = [
        {"type": "container", "name": "ghcr.io/sentientos/runtime:cpu"},
        {"type": "container", "name": "ghcr.io/sentientos/runtime:cuda12"},
    ]
    _write_bom("container-sbom.json", images)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
