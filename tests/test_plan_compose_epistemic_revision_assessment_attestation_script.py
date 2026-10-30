from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from scripts.compose_epistemic_revision_assessment_attestation import main
from sentientos.epistemic_revision_assessment_attestation import SCHEMA
from test_epistemic_revision_assessment_attestation import _prepared

pytestmark = pytest.mark.no_legacy_skip


def test_cli_verifies_signed_assessment_for_exact_suite_and_case(tmp_path: Path, capsys) -> None:
    revision_v2, revision_v3, reports, control, correction, attestation, key, fingerprint = _prepared()
    files: dict[str, Path] = {}
    values = {
        "v2": revision_v2,
        "v3": revision_v3,
        "case": asdict(correction),
        "control": control,
        "attestation": attestation,
    }
    for name, value in values.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        files[name] = path
    source_paths = []
    for index, report in enumerate(reports):
        path = tmp_path / f"series-{index}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        source_paths.append(str(path))
    key_path = tmp_path / "assessor-public-key.txt"
    key_path.write_text(key, encoding="utf-8")

    args = [str(files["v2"]), str(files["v3"]), str(files["case"]), *source_paths,
        "--pressure-control", str(files["control"]),
        "--attestation", str(files["attestation"]),
        "--assessor-public-key", str(key_path),
        "--expected-protocol-digest", "sha256:" + "d" * 64,
        "--expected-assessor-key-fingerprint", fingerprint]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == SCHEMA
    assert result["status"] == "suite_passed_with_assessor_attestation"
    assert result["assessment"]["signature_valid"] is True


def test_cli_without_attestation_reports_insufficient(tmp_path: Path, capsys) -> None:
    revision_v2, revision_v3, reports, control, correction, *_ = _prepared()
    values = {"v2": revision_v2, "v3": revision_v3, "case": asdict(correction),
        "control": control}
    files: dict[str, Path] = {}
    for name, value in values.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        files[name] = path
    source_paths = []
    for index, report in enumerate(reports):
        path = tmp_path / f"series-{index}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        source_paths.append(str(path))
    args = [str(files["v2"]), str(files["v3"]), str(files["case"]), *source_paths,
        "--pressure-control", str(files["control"])]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "insufficient"
    assert result["assessment"]["reasons"] == ["assessment_attestation_missing"]
