from __future__ import annotations

import json
from pathlib import Path

from scripts.emit_contract_status import emit_contract_status
from scripts.emit_stability_doctrine import emit_stability_doctrine
from sentientos.contract_sentinel import ContractSentinel, SentinelPolicy
from sentientos.vow_artifacts import ensure_vow_artifacts


def test_vow_artifacts_ensure_generates_manifest_when_missing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    manifest = tmp_path / "vow/immutable_manifest.json"
    calls: list[str] = []

    def fake_generate_manifest(*, output: Path, files=(), allow_missing_files: bool = False):  # type: ignore[no-untyped-def]
        _ = files, allow_missing_files
        calls.append(str(output))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text('{"ok":true}\n', encoding="utf-8")
        return {"ok": True}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sentientos.vow_artifacts.generate_immutable_manifest.generate_manifest", fake_generate_manifest)

    payload = ensure_vow_artifacts(manifest_path=manifest)

    assert payload["manifest_generated"] is True
    assert calls == [str(manifest)]
    assert manifest.exists()


def test_verify_audits_module_entrypoint_calls_scripts_module(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from sentientos import verify_audits

    captured: dict[str, object] = {}

    def fake_main(argv):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        return 7

    monkeypatch.setattr("scripts.verify_audits.main", fake_main)
    rc = verify_audits.main(["--strict"])
    assert rc == 7
    assert captured["argv"] == ["--strict"]


def test_emit_stability_doctrine_and_contract_rollup(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "vow").mkdir(parents=True, exist_ok=True)
    manifest = tmp_path / "vow/immutable_manifest.json"
    manifest.write_text('{"files":{}}\n', encoding="utf-8")

    class Done:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, check=False, capture_output=False, text=False):  # type: ignore[no-untyped-def]
        _ = check, capture_output, text
        cmd = tuple(command)
        if cmd[:4] == ("python", "-m", "sentientos.verify_audits", "--strict"):
            return Done(0, stdout="ok")
        if cmd[:2] == ("make", "mypy-forge"):
            return Done(0, stdout="ok")
        if cmd[:2] == ("make", "forge-ci"):
            return Done(0, stdout="ok")
        if cmd[:3] == ("git", "rev-parse", "--verify"):
            return Done(0, stdout="abc123\n")
        return Done(0)

    monkeypatch.setattr("scripts.emit_stability_doctrine.subprocess.run", fake_run)

    doctrine = emit_stability_doctrine()
    assert doctrine["toolchain"]["verify_audits_available"] is True
    assert doctrine["vow_artifacts"]["immutable_manifest_present"] is True

    status = emit_contract_status()
    domains = {item["domain_name"]: item for item in status["contracts"] if isinstance(item, dict) and isinstance(item.get("domain_name"), str)}
    assert "stability_doctrine" in domains


def test_sentinel_stability_mapping_triggers_repair(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/contract_status.json").write_text('{"previous":{}}\n', encoding="utf-8")
    sentinel = ContractSentinel(repo_root=tmp_path)
    policy = SentinelPolicy(enabled=True)
    snapshot = {
        "domains": {
            "stability_doctrine": {
                "doctrine_present": True,
                "verify_audits_available": False,
                "immutable_manifest_present": True,
            }
        }
    }
    trigger = sentinel._domain_trigger(domain="stability_doctrine", policy=policy, snapshot=snapshot)
    assert isinstance(trigger, dict)
    assert trigger.get("reason") == "toolchain_missing"
