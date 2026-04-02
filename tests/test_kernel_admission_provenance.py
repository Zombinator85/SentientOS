from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.kernel_admission_provenance import verify_kernel_admission_provenance

pytestmark = pytest.mark.no_legacy_skip


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def _decision(*, correlation_id: str, action_kind: str, final_disposition: str = "allow") -> dict[str, object]:
    return {
        "correlation_id": correlation_id,
        "action_kind": action_kind,
        "authority_class": "manifest_or_identity_mutation",
        "lifecycle_phase": "maintenance",
        "final_disposition": final_disposition,
        "delegate_checks_consulted": ["governor"],
        "execution_owner": "tests",
        "admission_decision_ref": f"kernel_decision:{correlation_id}",
    }


def _codes(payload: dict[str, object]) -> set[str]:
    return {str(issue["code"]) for issue in payload["issues"]}  # type: ignore[index]


def _categories(payload: dict[str, object]) -> set[str]:
    return {str(issue["category"]) for issue in payload["issues"]}  # type: ignore[index]


def test_legacy_manifest_missing_admission_is_non_blocking_in_baseline_mode(tmp_path: Path) -> None:
    _write_json(tmp_path / "vow/immutable_manifest.json", {"files": {}, "manifest_sha256": "abc"})

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    strict_payload = verify_kernel_admission_provenance(repo_root=tmp_path, strict=True)

    assert payload["ok"] is True
    assert payload["legacy_issue_count"] == 1
    assert payload["blocking_issue_count"] == 0
    assert "missing_manifest_admission_link" in _codes(payload)
    assert _categories(payload) == {"legacy_missing_admission_link"}

    assert strict_payload["ok"] is False
    assert strict_payload["blocking_issue_count"] == 1


def test_current_manifest_missing_admission_is_malformed_contract(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [_decision(correlation_id="corr-1", action_kind="generate_immutable_manifest")],
    )
    _write_json(tmp_path / "vow/immutable_manifest.json", {"files": {}, "manifest_sha256": "abc"})

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)

    assert payload["ok"] is False
    assert payload["legacy_issue_count"] == 0
    assert "missing_manifest_admission_link" in _codes(payload)
    assert "missing_expected_manifest_side_effect" in _codes(payload)
    assert "malformed_current_contract" in _categories(payload)


def test_manifest_with_bad_ref_is_malformed_contract(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [_decision(correlation_id="corr-2", action_kind="generate_immutable_manifest")],
    )
    _write_json(
        tmp_path / "vow/immutable_manifest.json",
        {
            "files": {},
            "manifest_sha256": "abc",
            "admission": {
                "correlation_id": "corr-2",
                "admission_decision_ref": "kernel_decision:wrong",
                "action_kind": "generate_immutable_manifest",
                "authority_class": "manifest_or_identity_mutation",
                "lifecycle_phase": "maintenance",
                "final_disposition": "allow",
                "execution_owner": "tests",
            },
        },
    )

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)

    assert payload["ok"] is False
    assert "invalid_manifest_admission_ref" in _codes(payload)
    assert "malformed_current_contract" in _categories(payload)


def test_valid_manifest_with_provenance_is_conforming(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [_decision(correlation_id="corr-3", action_kind="generate_immutable_manifest")],
    )
    _write_json(
        tmp_path / "vow/immutable_manifest.json",
        {
            "files": {},
            "manifest_sha256": "abc",
            "admission": {
                "correlation_id": "corr-3",
                "admission_decision_ref": "kernel_decision:corr-3",
                "action_kind": "generate_immutable_manifest",
                "authority_class": "manifest_or_identity_mutation",
                "lifecycle_phase": "maintenance",
                "final_disposition": "allow",
                "execution_owner": "tests",
            },
        },
    )

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)

    assert payload["ok"] is True
    assert payload["issue_count"] == 0
    assert payload["category_counts"] == {}


def test_correlation_collision_fails_in_both_modes(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [
            _decision(correlation_id="corr-4", action_kind="lineage_integrate"),
            _decision(correlation_id="corr-4", action_kind="generate_immutable_manifest"),
        ],
    )

    payload = verify_kernel_admission_provenance(repo_root=tmp_path)
    strict_payload = verify_kernel_admission_provenance(repo_root=tmp_path, strict=True)

    assert payload["ok"] is False
    assert strict_payload["ok"] is False
    assert "correlation_action_kind_collision" in _codes(payload)
    assert "unexpected_collision" in _categories(payload)


def test_forward_enforcement_classifies_legacy_as_debt_without_blocking(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "lineage/lineage.jsonl", [{"proposal_id": "legacy"}])
    payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    assert payload["ok"] is True
    assert payload["enforcement_class_counts"]["legacy_debt"] == 1  # type: ignore[index]
    first_issue = payload["issues"][0]  # type: ignore[index]
    assert first_issue["enforcement_class"] == "legacy_debt"


def test_strict_mode_is_stricter_than_forward_for_legacy_only_state(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "lineage/lineage.jsonl", [{"proposal_id": "legacy"}])
    forward_payload = verify_kernel_admission_provenance(repo_root=tmp_path, mode="forward-enforcement")
    strict_payload = verify_kernel_admission_provenance(repo_root=tmp_path, strict=True)
    assert forward_payload["ok"] is True
    assert strict_payload["ok"] is False
