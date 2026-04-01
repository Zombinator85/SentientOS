from __future__ import annotations

from pathlib import Path

from scripts import generate_immutable_manifest


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
