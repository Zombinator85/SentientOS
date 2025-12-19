from __future__ import annotations

from scripts import tooling_status


def test_tooling_status_emits_all() -> None:
    data = tooling_status.emit()
    assert {
        "pytest",
        "mypy",
        "verify_audits",
        "audit_immutability_verifier",
    }.issubset(set(data.keys()))
    assert data["pytest"]["classification"] == "mandatory"
    assert data["mypy"]["classification"] == "advisory"
    assert data["verify_audits"]["classification"] == "optional"
    assert data["audit_immutability_verifier"]["dependency"] == "/vow/immutable_manifest.json"


def test_tooling_status_render_result_includes_reason() -> None:
    result = tooling_status.render_result(
        "audit_immutability_verifier", status="skipped", reason="manifest_missing"
    )
    assert result["classification"] == "artifact-dependent"
    assert result["status"] == "skipped"
    assert result["reason"] == "manifest_missing"
