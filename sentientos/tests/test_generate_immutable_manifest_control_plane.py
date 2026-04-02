from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import generate_immutable_manifest


def test_manifest_generation_records_admission_linkage(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    captured_request = {}

    class _Decision:
        allowed = True
        reason_codes = ("admitted",)
        correlation_id = "manifest-allow"
        action_kind = "generate_immutable_manifest"
        actor = "operator_cli"
        delegated_outcomes = {"runtime_governor": {"allowed": True}}
        authority_class = type("Authority", (), {"value": "manifest_or_identity_mutation"})()
        current_phase = type("Phase", (), {"value": "maintenance"})()

        class outcome:
            value = "allow"

        @property
        def admission_decision_ref(self) -> str:
            return f"kernel_decision:{self.correlation_id}"

    class _Kernel:
        def set_phase(self, phase, *, actor="control_plane_kernel") -> None:  # noqa: ANN001
            return None

        def admit(self, request):  # noqa: ANN001
            captured_request["request"] = request
            return _Decision()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("scripts.generate_immutable_manifest.get_control_plane_kernel", lambda: _Kernel())
    (tmp_path / "NEWLEGACY.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "vow/config.yaml").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "vow/config.yaml").write_text("ok", encoding="utf-8")
    (tmp_path / "vow/invariants.yaml").write_text("ok", encoding="utf-8")
    (tmp_path / "vow/init.py").write_text("ok", encoding="utf-8")
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts/audit_immutability_verifier.py").write_text("ok", encoding="utf-8")
    (tmp_path / "scripts/verify_audits.py").write_text("ok", encoding="utf-8")

    manifest_path = tmp_path / "vow/immutable_manifest.json"
    assert generate_immutable_manifest.main(["--manifest", str(manifest_path)]) == 0
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["admission"]["correlation_id"] == "manifest-allow"
    assert payload["admission"]["admission_decision_ref"] == "kernel_decision:manifest-allow"
    assert payload["admission"]["execution_owner"] == "operator_cli"
    request = captured_request["request"]
    intent = request.metadata["protected_mutation_intent"]
    assert intent["domains"] == ["immutable_manifest_identity_writes"]
    assert intent["authority_classes"] == ["manifest_or_identity_mutation"]


def test_manifest_generation_blocked_when_kernel_denies(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    class _Decision:
        allowed = False
        reason_codes = ("runtime_governor:degraded_audit_trust_amendment_deferred",)
        correlation_id = "manifest-denied"

    class _Kernel:
        def set_phase(self, phase, *, actor="control_plane_kernel") -> None:  # noqa: ANN001
            return None

        def admit(self, request):  # noqa: ANN001
            return _Decision()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("scripts.generate_immutable_manifest.get_control_plane_kernel", lambda: _Kernel())

    manifest_path = tmp_path / "vow/immutable_manifest.json"
    assert generate_immutable_manifest.main(["--manifest", str(manifest_path)]) == 1
    assert not manifest_path.exists()


def test_generate_manifest_rejects_missing_required_provenance_before_write(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing_required_provenance_fields"):
        generate_immutable_manifest.generate_manifest(
            output=tmp_path / "vow/immutable_manifest.json",
            files=(),
            allow_missing_files=True,
            admission_context={"correlation_id": "manifest-x"},
        )
    assert not (tmp_path / "vow/immutable_manifest.json").exists()
