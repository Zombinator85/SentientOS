import pytest

from sentientos.codex_task_scaffold_path_planner import PlannerRequest, build_scaffold_request_payload, plan_codex_task_scaffold_paths


def test_planner_defaults() -> None:
    out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="Codex Task Scaffold Path Planner", subsystem_kind="developer_workflow_metadata"))
    assert out.status == "ready"
    assert out.module_path == "sentientos/codex_task_scaffold_path_planner.py"
    assert out.cli_path == "scripts/plan_codex_task_scaffold_path_planner.py"
    assert out.api_test_path == "tests/test_codex_task_scaffold_path_planner.py"


def test_planner_blocks_bad_paths() -> None:
    out = plan_codex_task_scaffold_paths(PlannerRequest(task_name="x", new_module=("../oops.py",)))
    assert out.status == "blocked"


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
