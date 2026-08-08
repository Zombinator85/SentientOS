from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from sentientos import maintenance_windows_deployment as deployment

pytestmark = pytest.mark.no_legacy_skip


def manifest(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": deployment.MANIFEST_SCHEMA,
        "repository_root": r"C:\Program Files\Sentient OS",
        "expected_repository_sha": "7d48c4dd21864c838fef4141b17af509b3a5a68f",
        "python_executable": r"C:\Program Files\Python 3.12\python.exe",
        "wake_configuration_path": r"D:\Sentient Custody\configuration\wake.json",
        "external_log_directory": r"D:\Sentient Custody\logs",
        "deployment_output_directory": r"D:\Sentient Custody\deployment",
        "task_name": "SentientOS Maintenance Wake",
        "working_directory": r"C:\Program Files\Sentient OS",
        "trigger_type": "interval", "trigger_interval_or_exact_schedule": "PT15M",
        "execution_timeout": "PT10M", "task_execution_account_mode": "system",
        "allow_on_battery": False, "wake_from_sleep": True,
        "missed_runs_start_later": False, "maximum_concurrent_instances": 1,
        "launcher_stdout_path": r"D:\Sentient Custody\logs\wake stdout.log",
        "launcher_stderr_path": r"D:\Sentient Custody\logs\wake stderr.log",
    }
    value.update(updates)
    return value


def test_render_retry_verify_and_artifact_semantics(tmp_path: Path, behavioral_witness) -> None:
    cfg = manifest(); output = tmp_path / "bundle"; first = deployment.render(cfg, output); before = {p.name: p.read_bytes() for p in output.iterdir()}
    second = deployment.render(cfg, output)
    assert first["artifact_digests"] == second["artifact_digests"]
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    assert deployment.verify(cfg, output)["status"] == "windows_deployment_ready"
    launcher = before["maintenance-wake.ps1"].decode()
    assert "[DateTimeOffset]::UtcNow" in launcher
    assert "$arguments = @($wakeScript, '--config', $wakeConfiguration, 'wake-once')" in launcher
    assert "Invoke-Expression" not in launcher and "git " not in launcher.lower()
    tree = ET.fromstring(before["maintenance-wake-task.xml"])
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert tree.findtext(".//t:MultipleInstancesPolicy", namespaces=ns) == "IgnoreNew"
    assert tree.findtext(".//t:Actions/t:Exec/t:Command", namespaces=ns) == "powershell.exe"
    joined = b"".join(before.values()).lower()
    assert b"password" not in joined and b"credential" not in joined and b"token" not in joined
    behavioral_witness.record("maintenance_windows_deployment", "successful_bundle", {
        "verified": True, "retry_bytes_identical": True, "single_instance": True,
        "scheduler_mutation_performed": False, "artifact_count": 3,
    })


def test_conflicting_output_blocks(tmp_path: Path) -> None:
    deployment.render(manifest(), tmp_path)
    (tmp_path / "maintenance-wake.ps1").write_text("conflict")
    with pytest.raises(ValueError, match="conflicting_output"):
        deployment.render(manifest(), tmp_path)


@pytest.mark.parametrize("field", sorted(deployment.PATH_FIELDS))
def test_all_manifest_paths_must_be_absolute_windows_paths(field: str) -> None:
    with pytest.raises(ValueError, match="absolute_windows_path"):
        deployment.validate_manifest(manifest(**{field: "relative/path"}))


def test_rejects_unsupported_policy_credentials_and_repository_custody() -> None:
    with pytest.raises(ValueError, match="maximum_concurrent_instances"):
        deployment.validate_manifest(manifest(maximum_concurrent_instances=2))
    with pytest.raises(ValueError, match="external_to_repository"):
        deployment.validate_manifest(manifest(external_log_directory=r"C:\Program Files\Sentient OS\logs"))
    bad = manifest(); bad["password"] = "not-allowed"
    with pytest.raises(ValueError, match="invalid_closed_manifest"):
        deployment.validate_manifest(bad)


def test_print_commands_are_data_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("process or scheduler mutation attempted")
    monkeypatch.setattr("subprocess.run", forbidden)
    cfg = manifest()
    install = deployment.print_install_command(cfg); uninstall = deployment.print_uninstall_command(cfg); preflight = deployment.print_preflight_command(cfg)
    assert install["argv"][:2] == ["schtasks.exe", "/Create"]
    assert uninstall["argv"][:2] == ["schtasks.exe", "/Delete"]
    assert all(not result["executed"] and not result["scheduler_mutation_performed"] for result in (install, uninstall, preflight))
    assert preflight["commands"][0]["argv"][-2:] == ["rev-parse", "HEAD"]
    assert [x["argv"][-1] for x in preflight["commands"][2:]] == ["doctor", "wake-once", "inspect-receipts"]


def test_manifest_digest_and_rendered_digest_tampering_block(tmp_path: Path) -> None:
    cfg = deployment.validate_manifest(manifest())
    bad = dict(cfg); bad["expected_repository_sha"] = "1" * 40
    with pytest.raises(ValueError, match="manifest_digest_mismatch"):
        deployment.validate_manifest(bad)
    deployment.render(cfg, tmp_path)
    index = json.loads((tmp_path / deployment.INDEX_NAME).read_text())
    index["manifest_digest"] = "sha256:" + "0" * 64
    (tmp_path / deployment.INDEX_NAME).write_text(json.dumps(index))
    assert deployment.verify(cfg, tmp_path)["status"] == "windows_deployment_blocked"
