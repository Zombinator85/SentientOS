from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import emit_contract_status

pytestmark = pytest.mark.no_legacy_skip


def test_protected_mutation_summary_handles_malformed_nested_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        emit_contract_status,
        "verify_kernel_admission_provenance",
        lambda **_kwargs: {"summary": "malformed"},
    )

    status = emit_contract_status._protected_mutation_proof_status(
        git_sha="test-sha",
        repo_root=tmp_path,
    )

    assert status["classification_counts"] == {}
    assert status["has_current_contract_violations"] is False
    assert (tmp_path / "glow/contracts/protected_mutation_proof_status.json").exists()


def test_stability_doctrine_handles_malformed_nested_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contracts = tmp_path / "glow/contracts"
    contracts.mkdir(parents=True)
    (contracts / "stability_doctrine.json").write_text(
        json.dumps({"toolchain": "malformed", "vow_artifacts": []}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    status = emit_contract_status._stability_doctrine_status(git_sha="test-sha")

    assert status["verify_audits_available"] is False
    assert status["immutable_manifest_present"] is False
    assert status["immutable_manifest_sha256"] is None
