from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sentientos.gaming_companion_process_profile import (
    CompanionProcessProfileError,
    PROCESS_PROFILE_SCHEMA,
    load_companion_process_launch_profiles,
)

pytestmark = pytest.mark.no_legacy_skip


def _profile() -> dict[str, object]:
    return {
        "schema_version": PROCESS_PROFILE_SCHEMA,
        "roles": {
            "windows_edge": {
                "argv": [
                    r"C:\Program Files\SentientOS\.venv\Scripts\python.exe",
                    "-m", "sentientos.gaming_companion_role_entrypoint",
                    "--role", "windows_edge", "--manifest",
                    r"C:\ProgramData\SentientOS\deployment.json",
                    "--provider", "sentientos_platform.windows:build_edge",
                    "--launch-authorizer", "sentientos_platform.authority:authorize_edge",
                    "--poll-interval", "0.25",
                ],
                "working_directory": r"C:\Program Files\SentientOS",
                "environment": {"SENTIENTOS_COMPANION_ROLE": "windows_edge"},
                "startup_timeout_seconds": 20,
                "shutdown_timeout_seconds": 5,
            },
            "wsl_core": {
                "argv": [
                    r"C:\Windows\System32\wsl.exe", "--distribution", "Ubuntu-SentientOS",
                    "--exec", "/srv/sentientos/.venv/bin/python",
                    "-m", "sentientos.gaming_companion_role_entrypoint",
                    "--role", "wsl_core", "--manifest", "/etc/sentientos/deployment.json",
                    "--provider", "sentientos_platform.wsl:build_core",
                    "--launch-authorizer", "sentientos_platform.authority:authorize_core",
                ],
                "working_directory": r"C:\Program Files\SentientOS",
                "environment": {"SENTIENTOS_COMPANION_ROLE": "wsl_core"},
                "startup_timeout_seconds": 25,
                "shutdown_timeout_seconds": 8,
            },
        },
    }


def _write_profile(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")
    os.chmod(path, 0o600)


def test_profile_loader_builds_closed_windows_and_wsl_role_specs(tmp_path: Path) -> None:
    path = tmp_path / "process-profile.json"
    _write_profile(path, _profile())

    specs = load_companion_process_launch_profiles(path, system_name="Windows")

    assert set(specs) == {"windows_edge", "wsl_core"}
    assert specs["windows_edge"].role == "windows_edge"
    assert specs["windows_edge"].argv[1:3] == (
        "-m", "sentientos.gaming_companion_role_entrypoint")
    assert specs["wsl_core"].argv[1:5] == (
        "--distribution", "Ubuntu-SentientOS", "--exec",
        "/srv/sentientos/.venv/bin/python")
    assert specs["wsl_core"].environment == {"SENTIENTOS_COMPANION_ROLE": "wsl_core"}


def test_profile_loader_rejects_extra_command_arguments_and_secret_environment(
        tmp_path: Path) -> None:
    path = tmp_path / "process-profile.json"
    profile = _profile()
    roles = profile["roles"]
    assert isinstance(roles, dict)
    edge = roles["windows_edge"]
    assert isinstance(edge, dict)
    edge["argv"].extend(["--api-token", "secret-looking-value"])
    _write_profile(path, profile)

    with pytest.raises(CompanionProcessProfileError,
                       match="companion_process_profile_role_command_invalid"):
        load_companion_process_launch_profiles(path, system_name="Windows")

    profile = _profile()
    roles = profile["roles"]
    assert isinstance(roles, dict)
    edge = roles["windows_edge"]
    assert isinstance(edge, dict)
    edge["environment"]["API_TOKEN"] = "forbidden"
    _write_profile(path, profile)
    with pytest.raises(CompanionProcessProfileError,
                       match="companion_process_profile_environment_invalid"):
        load_companion_process_launch_profiles(path, system_name="Windows")


def test_profile_loader_rejects_duplicate_fields_and_untrusted_hosts(tmp_path: Path) -> None:
    path = tmp_path / "process-profile.json"
    path.write_text('{"schema_version":"ignored","schema_version":"ignored-too"}',
                    encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(CompanionProcessProfileError,
                       match="companion_process_profile_invalid_json"):
        load_companion_process_launch_profiles(path, system_name="Windows")

    _write_profile(path, _profile())
    with pytest.raises(CompanionProcessProfileError,
                       match="companion_process_profile_windows_host_required"):
        load_companion_process_launch_profiles(path, system_name="Linux")


def test_profile_loader_rejects_path_escape_and_wrong_role_binding(tmp_path: Path) -> None:
    path = tmp_path / "process-profile.json"
    profile = _profile()
    roles = profile["roles"]
    assert isinstance(roles, dict)
    core = roles["wsl_core"]
    assert isinstance(core, dict)
    core["argv"][10] = "/etc/sentientos/../outside.json"
    _write_profile(path, profile)
    with pytest.raises(CompanionProcessProfileError,
                       match="companion_process_profile_manifest_path_invalid"):
        load_companion_process_launch_profiles(path, system_name="Windows")

    profile = _profile()
    roles = profile["roles"]
    assert isinstance(roles, dict)
    core = roles["wsl_core"]
    assert isinstance(core, dict)
    core["argv"][8] = "windows_edge"
    _write_profile(path, profile)
    with pytest.raises(CompanionProcessProfileError,
                       match="companion_process_profile_role_command_invalid"):
        load_companion_process_launch_profiles(path, system_name="Windows")
