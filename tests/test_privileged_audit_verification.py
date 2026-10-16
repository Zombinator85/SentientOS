from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_privileged_audit_verification as verification

pytestmark = pytest.mark.no_legacy_skip


def test_privileged_audit_wrapper_rejects_non_root_before_running_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verification.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        verification.subprocess, "run",
        lambda *_args, **_kwargs: pytest.fail("unprivileged invocation ran a command"),
    )

    with pytest.raises(PermissionError,
                       match="privileged_audit_verification_requires_actual_root"):
        verification.run_verification(
            tmp_path, expected_sha="a" * 40,
            output=Path("glow/audits/privileged_audit_verification.json"),
        )


def test_required_quality_gate_binds_root_audits_to_exact_checkout() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/required-quality-gate.yml").read_text()
    implementation = (root / "scripts/run_privileged_audit_verification.py").read_text()

    assert 'test "$(sudo -n id -u)" = "0"' in workflow
    assert "sudo -n env" in workflow
    assert "run_privileged_audit_verification.py" in workflow
    assert '"$GITHUB_SHA"' in workflow
    assert workflow.index("Run strict audits with actual Administrator authority") < workflow.index(
        "python -m scripts.run_tests")
    assert "verify_audits.py\", \"--strict" in implementation
    assert "scripts/audit_immutability_verifier.py" in implementation
    assert "head != expected_sha" in implementation
    assert "source_before == source_after" in implementation
    assert "head == final_head and tree == final_tree" in implementation
    assert '"effective_uid": os.geteuid()' in implementation
    assert '"--untracked-files=all"' in implementation
    assert "_validate_audit_results(root)" in implementation
    assert "|| true" not in workflow


def test_root_audit_result_is_uploaded_with_quality_gate_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/required-quality-gate.yml").read_text()
    upload = workflow.split("- name: Upload quality-gate evidence", 1)[1]

    assert "if: always()" in upload
    assert "glow/audits/privileged_audit_verification.json" in upload
    assert "glow/audits/verify_audits_result.json" in upload
    assert "glow/audits/audit_immutability_result.json" in upload
    assert "glow/contracts/strict_audit_recovery_links.json" in upload
    assert "glow/contracts/strict_audit_manifest.json" in upload


def _write_audit_evidence(root: Path) -> None:
    evidence = {
        "glow/audits/verify_audits_result.json": {
            "tool": "verify_audits", "ok": True,
        },
        "glow/audits/audit_immutability_result.json": {
            "tool": "audit_immutability_verifier", "ok": True,
        },
        "glow/contracts/strict_audit_status.json": {"blocking": False},
        "glow/contracts/strict_audit_breakdown.json": {"bucket": "healthy_strict"},
        "glow/contracts/strict_audit_recovery_links.json": {"links": {}},
        "glow/contracts/strict_audit_manifest.json": {"artifacts": {}},
    }
    for relative, payload in evidence.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    digests = {
        "schema_version": 1,
        "generated_at": "fixed",
        "strict_audit_status_digest": verification._stable_json_digest(
            evidence["glow/contracts/strict_audit_status.json"]),
        "strict_audit_breakdown_digest": verification._stable_json_digest(
            evidence["glow/contracts/strict_audit_breakdown.json"]),
        "strict_audit_recovery_links_digest": verification._stable_json_digest(
            evidence["glow/contracts/strict_audit_recovery_links.json"]),
        "strict_audit_manifest_digest": verification._stable_json_digest(
            evidence["glow/contracts/strict_audit_manifest.json"]),
    }
    digests["strict_audit_digest"] = verification._stable_json_digest(digests)
    digest_path = root / "glow/contracts/final_strict_audit_digest.json"
    digest_path.write_text(json.dumps(digests), encoding="utf-8")


def test_audit_result_validation_requires_successful_receipts_and_bound_contracts(
    tmp_path: Path,
) -> None:
    _write_audit_evidence(tmp_path)

    result = verification._validate_audit_results(tmp_path)

    assert result["valid"] is True
    assert result["strict_audit_ok"] is True
    assert result["immutability_ok"] is True
    assert result["strict_audit_nonblocking"] is True


def test_audit_result_validation_rejects_failed_receipt_and_stale_digest(
    tmp_path: Path,
) -> None:
    _write_audit_evidence(tmp_path)
    receipt = tmp_path / "glow/audits/verify_audits_result.json"
    receipt.write_text(json.dumps({"tool": "verify_audits", "ok": False}), encoding="utf-8")

    failed_receipt = verification._validate_audit_results(tmp_path)
    assert failed_receipt["valid"] is False
    assert "strict_audit_result_missing_or_not_ok" in failed_receipt["errors"]

    _write_audit_evidence(tmp_path)
    status = tmp_path / "glow/contracts/strict_audit_status.json"
    status.write_text(json.dumps({"blocking": True}), encoding="utf-8")
    stale_digest = verification._validate_audit_results(tmp_path)
    assert stale_digest["valid"] is False
    assert "strict_audit_status_missing_or_blocking" in stale_digest["errors"]
    assert "strict_audit_evidence_digest_mismatch" in stale_digest["errors"]
