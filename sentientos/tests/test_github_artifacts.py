from __future__ import annotations

from pathlib import Path

from sentientos.github_artifacts import parse_bundle


def test_parse_bundle_tolerates_missing_files(tmp_path: Path) -> None:
    bundle = parse_bundle(tmp_path)

    assert bundle.source == "remote"
    assert bundle.errors
    assert any(err.startswith("missing:") for err in bundle.errors)


def test_parse_bundle_tolerates_corrupt_json(tmp_path: Path) -> None:
    (tmp_path / "contract_status.json").write_text("{oops", encoding="utf-8")
    (tmp_path / "stability_doctrine.json").write_text('{"baseline_integrity_ok": true}', encoding="utf-8")
    (tmp_path / "ci_baseline.json").write_text('{"failed_count": 0}', encoding="utf-8")
    (tmp_path / "artifact_metadata.json").write_text('{"sha": "abc"}', encoding="utf-8")

    bundle = parse_bundle(tmp_path)

    assert "invalid_json:contract_status.json" in bundle.errors
    assert "stability_doctrine.json" in bundle.parsed
