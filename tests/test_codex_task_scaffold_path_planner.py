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
