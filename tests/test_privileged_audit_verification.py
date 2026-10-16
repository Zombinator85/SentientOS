from __future__ import annotations

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
    assert "|| true" not in workflow


def test_root_audit_result_is_uploaded_with_quality_gate_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/required-quality-gate.yml").read_text()
    upload = workflow.split("- name: Upload quality-gate evidence", 1)[1]

    assert "if: always()" in upload
    assert "glow/audits/privileged_audit_verification.json" in upload
    assert "glow/audits/verify_audits_result.json" in upload
    assert "glow/audits/audit_immutability_result.json" in upload
