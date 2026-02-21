from __future__ import annotations

import json
from pathlib import Path

from scripts.emit_contract_manifest import OPTIONAL_FILES, REQUIRED_FILES, emit_manifest
from sentientos.doctrine_identity import local_doctrine_identity


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_doctrine_identity_ignores_forge_ratchet_status(tmp_path: Path) -> None:
    contracts = tmp_path / "glow/contracts"
    _write_json(contracts / "stability_doctrine.json", {"schema_version": 1})
    _write_json(contracts / "contract_status.json", {"schema_version": 1, "contracts": []})
    _write_json(contracts / "artifact_metadata.json", {"schema_version": 1, "sha": "abc"})
    _write_json(contracts / "ci_baseline.json", {"schema_version": 1, "passed": True})
    _write_json(contracts / "forge_progress_baseline.json", {"schema_version": 1, "goals": []})

    emit_manifest(contracts, git_sha="abc", created_at="2026-01-01T00:00:00Z")
    first = local_doctrine_identity(tmp_path).bundle_sha256

    ratchet_path = tmp_path / "glow/forge/ratchets/mypy_ratchet_status.json"
    _write_json(ratchet_path, {"status": "ok", "new_error_count": 0})

    second = local_doctrine_identity(tmp_path).bundle_sha256

    assert first
    assert first == second


def test_contract_manifest_lists_exclude_ratchet_status() -> None:
    listed = [*REQUIRED_FILES, *OPTIONAL_FILES]
    assert "mypy_ratchet_status.json" not in listed
    assert all("ratchet" not in name for name in listed)
    assert all("/" not in name for name in listed)
