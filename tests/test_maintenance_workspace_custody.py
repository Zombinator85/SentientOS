from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos import maintenance_workspace_custody as custody


def config(tmp_path: Path) -> custody.WorkspaceCustodyConfig:
    git = Path("/usr/bin/git").resolve(strict=True)
    return custody.WorkspaceCustodyConfig(
        configuration_id="custody:test",
        repository_identity="Zombinator85/SentientOS",
        repository_root=Path.cwd().resolve(),
        external_workspace_root=tmp_path / "workspaces",
        external_state_root=tmp_path / "state",
        git_executable=git,
        git_executable_digest="sha256:" + hashlib.sha256(git.read_bytes()).hexdigest(),
        maximum_instruction_bytes=4096,
        process_timeout_seconds=30,
        configuration_constraints=("detached_exact_base",),
    )


def test_closed_config_contains_no_backend_transport_fields(tmp_path: Path) -> None:
    value = config(tmp_path).to_dict()
    assert custody.WorkspaceCustodyConfig.from_mapping(value).to_dict() == value
    assert not ({"codex_executable", "codex_home", "model", "activation"} & set(value))


def test_wrong_git_identity_and_repository_escape_fail_closed(tmp_path: Path) -> None:
    value = config(tmp_path).to_dict()
    value["git_executable_digest"] = "sha256:" + "0" * 64
    value["configuration_digest"] = custody.digest({k: v for k, v in value.items() if k != "configuration_digest"})
    with pytest.raises(ValueError, match="git_executable_digest_mismatch"):
        custody.WorkspaceCustodyConfig.from_mapping(value)
    escaped = config(tmp_path).__class__(**{**config(tmp_path).__dict__, "external_workspace_root": Path.cwd() / "bad"})
    with pytest.raises(ValueError, match="inside_repository"):
        escaped.validate()


def test_symlink_custody_root_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"; target.mkdir()
    link = tmp_path / "link"; link.symlink_to(target, target_is_directory=True)
    value = config(tmp_path).to_dict(); value["external_workspace_root"] = str(link)
    value["configuration_digest"] = custody.digest({k: v for k, v in value.items() if k != "configuration_digest"})
    with pytest.raises(ValueError, match="symlink"):
        custody.WorkspaceCustodyConfig.from_mapping(value)
