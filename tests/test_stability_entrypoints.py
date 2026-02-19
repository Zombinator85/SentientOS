from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import emit_stability_doctrine
from sentientos import vow_artifacts

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def test_pyproject_exposes_legacy_console_scripts() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    scripts = payload["project"]["scripts"]

    assert scripts["verify_audits"] == "sentientos.verify_audits:main"
    assert scripts["audit_immutability_verifier"] == "sentientos.vow_artifacts:run_immutability_verifier_main"


def test_verify_audits_shim_forwards_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool) -> object:
        calls.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)

    shim = Path("scripts/verify_audits")
    source = shim.read_text(encoding="utf-8")
    argv = [str(shim), "--strict", "logs"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        exec(compile(source, str(shim), "exec"), {"__name__": "__main__"})

    assert exc.value.code == 0
    assert calls == [[sys.executable, "-m", "sentientos.verify_audits", "--strict", "logs"]]


def test_audit_immutability_shim_forwards_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool) -> object:
        calls.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)

    shim = Path("scripts/audit_immutability_verifier")
    source = shim.read_text(encoding="utf-8")
    argv = [str(shim), "--manifest", "tmp/manifest.json"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        exec(compile(source, str(shim), "exec"), {"__name__": "__main__"})

    assert exc.value.code == 0
    assert calls == [[sys.executable, "-m", "sentientos.vow_artifacts", "verify", "--manifest", "tmp/manifest.json"]]


def test_immutability_verifier_ensures_manifest_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "immutable_manifest.json"
    ensured: list[Path] = []

    def fake_ensure(*, manifest_path: Path | None = None) -> dict[str, object]:
        assert manifest_path is not None
        ensured.append(manifest_path)
        manifest_path.write_text('{"files": {}, "manifest_sha256": "x"}', encoding="utf-8")
        return {"manifest_generated": True, "manifest_path": str(manifest_path)}

    import scripts.audit_immutability_verifier as aiv

    def fake_verify_once(*, manifest_path: Path, allow_missing_manifest: bool, logger):
        assert manifest_path.exists()
        return aiv.AuditCheckOutcome("passed", recorded_events=[])


    monkeypatch.setattr(vow_artifacts, "ensure_vow_artifacts", fake_ensure)
    monkeypatch.setattr(aiv, "verify_once", fake_verify_once)
    monkeypatch.chdir(tmp_path)

    assert aiv.main(["--manifest", str(manifest)]) == 0
    assert ensured == [manifest]


def test_emit_stability_doctrine_records_module_and_console_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(command: list[str]) -> tuple[bool, str]:
        if command[:3] == ["python", "-m", "sentientos.verify_audits"]:
            return (True, "module ok")
        if command[:1] == ["verify_audits"]:
            return (False, "not installed")
        return (True, "ok")

    monkeypatch.setattr(emit_stability_doctrine, "_run", fake_run)
    monkeypatch.setattr(emit_stability_doctrine, "_resolve_manifest_path", lambda: tmp_path / "immutable_manifest.json")
    monkeypatch.setattr(emit_stability_doctrine, "_git_sha", lambda: "abc123")

    output = tmp_path / "contract.json"
    payload = emit_stability_doctrine.emit_stability_doctrine(output)

    assert payload["toolchain"]["audit_tool_module_ok"] is True
    assert payload["toolchain"]["audit_tool_console_ok"] is False

    payload_again = emit_stability_doctrine.emit_stability_doctrine(output)
    assert payload_again["toolchain"]["audit_tool_module_ok"] is True
    assert payload_again["toolchain"]["audit_tool_console_ok"] is False
