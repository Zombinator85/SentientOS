from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_immutability_verifier as aiv
from scripts.generate_immutable_manifest import generate_manifest


def test_manifest_generation_is_deterministic(tmp_path: Path) -> None:
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("stable-data", encoding="utf-8")

    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"

    generate_manifest(output=out_a, files=(tracked,))
    generate_manifest(output=out_b, files=(tracked,))

    first = json.loads(out_a.read_text(encoding="utf-8"))
    second = json.loads(out_b.read_text(encoding="utf-8"))
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert first["files"] == second["files"]


def test_audit_verifier_runs_without_skip_with_generated_manifest(tmp_path: Path) -> None:
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("stable-data", encoding="utf-8")
    manifest = tmp_path / "immutable_manifest.json"
    generate_manifest(output=manifest, files=(tracked,))

    events: list[dict] = []
    outcome = aiv.verify_once(manifest_path=manifest, logger=events.append)

    assert outcome.status == "passed"
    checks = [e for e in events if e.get("event") == "immutability_check"]
    assert checks
    assert all(e.get("status") == "verified" for e in checks)
