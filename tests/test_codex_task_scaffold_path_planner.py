import re
from pathlib import Path

import pytest

from sentientos.codex_task_scaffold_path_planner import (
    ALLOWED_PATH_ROOTS,
    PACKAGED_SOURCE_ROOTS,
    WORKFLOW_ROOTS,
    PlannerRequest,
    build_scaffold_request_payload,
    plan_codex_task_scaffold_paths,
)


def test_planner_defaults() -> None:
    out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="Codex Task Scaffold Path Planner", subsystem_kind="developer_workflow_metadata"))
    assert out.status == "ready"
    assert out.module_path == "sentientos/codex_task_scaffold_path_planner.py"
    assert out.cli_path == "scripts/plan_codex_task_scaffold_path_planner.py"
    assert out.api_test_path == "tests/test_codex_task_scaffold_path_planner.py"


def test_planner_blocks_bad_paths() -> None:
    out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="x", new_module=("../oops.py",)))
    assert out.status == "blocked"


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("module_path", (
    "sentientos/example.py",
    "api/example.py",
    "gui/example.py",
    "apps/example.py",
    "scripts/example.py",
    "tests/test_example.py",
    "docs/example.md",
    "artifacts/example.json",
))
def test_planner_accepts_each_canonical_path_root(module_path: str) -> None:
    out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="root classification", new_module=(module_path,)))
    assert out.status in {"ready", "ready_with_warnings"}
    assert "path_outside_allowed_roots" not in out.blocker_codes


@pytest.mark.no_legacy_skip
def test_planner_accepts_existing_api_actuator_as_implementation_target() -> None:
    out = plan_codex_task_scaffold_paths(
        PlannerRequest(task_name="actuator path classification", new_module=("api/actuator.py",))
    )
    assert out.module_path == "api/actuator.py"
    assert "path_outside_allowed_roots" not in out.blocker_codes
    assert out.status in {"ready", "ready_with_warnings"}


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("module_path", (
    "../api/actuator.py",
    "/api/actuator.py",
    "api_evil/actuator.py",
    "apix/actuator.py",
    "sentientos_backup/example.py",
    "unknown_root/file.py",
    ".github/workflows/change.yml",
    ".env",
    "api/bad;name.py",
))
def test_planner_rejects_unsafe_or_noncanonical_roots(module_path: str) -> None:
    out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="root classification", new_module=(module_path,)))
    assert out.status == "blocked"
    assert set(out.blocker_codes) & {"path_traversal_or_metacharacters", "path_outside_allowed_roots"}


def _pyproject_packaged_roots(text: str) -> tuple[set[str], set[str]]:
    poetry_block = text.split("packages = [", 1)[1].split("]", 1)[0]
    poetry = set(re.findall(r'include\s*=\s*"([a-zA-Z0-9_]+)"', poetry_block))
    section = re.search(r"(?ms)^\[tool\.setuptools\.packages\.find\]\n(.*?)(?=^\[|\Z)", text)
    assert section is not None
    setuptools_block = section.group(1)
    setuptools = set(re.findall(r'"([a-zA-Z0-9_]+)"', setuptools_block.split("include =", 1)[1]))
    return poetry, setuptools


@pytest.mark.no_legacy_skip
def test_planner_packaged_roots_match_canonical_packaging_metadata() -> None:
    poetry, setuptools = _pyproject_packaged_roots(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert poetry == setuptools == set(PACKAGED_SOURCE_ROOTS)
    assert ALLOWED_PATH_ROOTS == PACKAGED_SOURCE_ROOTS | WORKFLOW_ROOTS


def test_scaffold_request_payload() -> None:
    req = PlannerRequest(task_name="x", subsystem_kind="developer_workflow_metadata")
    out = plan_codex_task_scaffold_paths(req)
    payload = build_scaffold_request_payload(req, out)
    assert payload["new_module_path"][0].startswith("sentientos/")


@pytest.mark.no_legacy_skip
def test_planner_distinguishes_prohibitions_from_authority_requests() -> None:
    allowed = (
        "without provider inference",
        "provider inference is forbidden",
        "do not call OpenAI",
        "do not call GitHub APIs",
        "no network access",
        "subprocess execution must remain disabled",
        "shell execution is prohibited",
        "do not invoke the action wing",
    )
    blocked = (
        "use provider inference",
        "call OpenAI for inference",
        "use GitHub API to publish",
        "spawn a subprocess",
        "execute shell commands from the library",
        "invoke the action wing",
        "do not hesitate to use provider inference",
    )
    for goal in allowed:
        out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="classification repair", task_goal=goal))
        assert "forbidden_authority_surface_requested" not in out.blocker_codes
    for goal in blocked:
        out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="classification repair", task_goal=goal))
        assert out.status == "blocked"
        assert "forbidden_authority_surface_requested" in out.blocker_codes


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(
    "goal",
    (
        "remove shell-based execution",
        "eliminate shell invocation",
        "disable subprocess-based fallback",
        "remove provider fallback",
        "eliminate network egress",
        "prohibit GitHub publication from this runtime path",
        "replace an OpenAI-backed implementation with a local non-provider implementation",
        "remove action-wing invocation from this component",
        "harden an existing shell surface by deleting its execution bridge",
        "REMOVE SHELL INVOCATION",
    ),
)
def test_planner_allows_unambiguous_authority_reduction(goal: str) -> None:
    out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="classification repair", task_goal=goal))
    assert out.status in {"ready", "ready_with_warnings"}
    assert "forbidden_authority_surface_requested" not in out.blocker_codes


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(
    "goal",
    (
        "replace local inference with OpenAI",
        "replace the current runner with shell execution",
        "harden publication by using GitHub APIs directly",
        "improve reliability by spawning a subprocess",
        "migrate to provider inference",
        "add a network fallback",
        "enable shell execution with stricter validation",
        "remove shell execution from the actuator, then call OpenAI to validate the result",
        "disable provider fallback but enable network telemetry",
        "remove shell execution. Then call OpenAI to validate the result",
        "disable provider fallback; enable network telemetry",
        "eliminate shell invocation\nspawn a subprocess",
        "remove restrictions on shell execution",
        "disable blocking of provider inference",
        "eliminate prohibition on network access",
        "modify shell handling",
        "refactor subprocess support",
        "harden the subprocess path and then run it",
        "restrict provider inference but allow it for retries",
        "replace one network path by enabling another network path",
    ),
)
def test_planner_blocks_ambiguous_expanding_and_mixed_authority_intent(goal: str) -> None:
    out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="classification repair", task_goal=goal))
    assert out.status == "blocked"
    assert "forbidden_authority_surface_requested" in out.blocker_codes


@pytest.mark.no_legacy_skip
def test_planner_reduction_is_clause_local_across_all_request_text_fields() -> None:
    for field in ("task_name", "task_goal", "preset_id", "subsystem_kind"):
        values = {"task_name": "classification repair", field: "remove shell invocation"}
        out = plan_codex_task_scaffold_paths(PlannerRequest(**values))
        assert "forbidden_authority_surface_requested" not in out.blocker_codes

    out = plan_codex_task_scaffold_paths(
        PlannerRequest(task_name="remove shell invocation", task_goal="call OpenAI for validation")
    )
    assert "forbidden_authority_surface_requested" in out.blocker_codes


@pytest.mark.no_legacy_skip
def test_planner_actuator_hardening_regression_is_reduction_not_exercise() -> None:
    reduction = plan_codex_task_scaffold_paths(
        PlannerRequest(
            task_name="actuator execution bridge removal",
            task_goal=(
                "Replace existing shell-string execution with one argv-authorized, argv-executed contract; "
                "shell interpretation and subprocess shell bridging must not be used."
            ),
        )
    )
    exercise = plan_codex_task_scaffold_paths(
        PlannerRequest(task_name="actuator change", task_goal="Enable shell execution for actuator commands.")
    )
    assert reduction.status in {"ready", "ready_with_warnings"}
    assert "forbidden_authority_surface_requested" not in reduction.blocker_codes
    assert exercise.status == "blocked"
    assert "forbidden_authority_surface_requested" in exercise.blocker_codes
