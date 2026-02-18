"""Shared CathedralForge data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping


@dataclass(slots=True)
class ForgePhase:
    summary: str
    touched_paths_globs: list[str]
    commands_to_run: list[str]
    expected_contract_impact: str


@dataclass(slots=True)
class CommandSpec:
    step: str
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 600


@dataclass(slots=True)
class CommandResult:
    step: str
    argv: list[str]
    cwd: str
    env_overlay: dict[str, str]
    timeout_seconds: int
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(slots=True)
class GoalProfile:
    name: str
    test_command: Callable[[str], list[str]]
    test_command_display: str


@dataclass(slots=True)
class ForgeSession:
    session_id: str
    root_path: str
    strategy: str
    branch_name: str
    env_python_path: str = ""
    env_venv_path: str = ""
    env_reused: bool = False
    env_install_summary: str = ""
    env_cache_key: str = ""
    preserved_on_failure: bool = False
    cleanup_performed: bool = False


@dataclass(slots=True)
class ApplyResult:
    status: str
    step_results: list[CommandResult]
    summary: str


@dataclass(slots=True)
class ForgeCheckResult:
    status: str
    summary: str


@dataclass(slots=True)
class ForgeTestResult:
    status: str
    command: str
    summary: str


@dataclass(slots=True)
class ForgePreflight:
    contract_drift: ForgeCheckResult
    contract_status_path: str
    contract_status_embedded: dict[str, object]


def merge_env(base: Mapping[str, str], overlay: Mapping[str, str]) -> dict[str, str]:
    env = dict(base)
    env.update(overlay)
    return env
