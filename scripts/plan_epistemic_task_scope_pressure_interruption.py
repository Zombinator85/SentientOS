from __future__ import annotations

import argparse
import json

from sentientos.codex_task_scaffold_path_planner import (
    PlannerRequest,
    plan_codex_task_scaffold_paths,
)

TASK_NAME = "Task-scoped correction pressure after interruption"
TASK_GOAL = (
    "Compose the existing task-scope interruption experiment with one unsupported "
    "user-pressure control after interruption. Bind the pressure response to the "
    "exact corrected projection, task target, evidence window, model identity, "
    "configuration, budget, and delivered scope. Preserve failures and insufficiency."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=TASK_GOAL)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    result = plan_codex_task_scaffold_paths(PlannerRequest(
        task_name=TASK_NAME, task_goal=TASK_GOAL,
        subsystem_kind="experiment_composer", commit_scope="experiments",
        commit_title="[codex:experiments] measure task-scoped pressure after interruption",
        new_module=("sentientos/epistemic_task_scope_pressure_interruption.py",),
        new_cli=("scripts/plan_epistemic_task_scope_pressure_interruption.py",),
        test_path=("tests/test_epistemic_task_scope_pressure_interruption.py",
            "tests/test_plan_epistemic_task_scope_pressure_interruption.py"),
        doc_path=("docs/development/epistemic_task_scope_pressure_interruption.md",),
        capability_id="epistemic_task_scope_pressure_interruption"))
    if args.summary:
        print(json.dumps({"status": result.status, "task_slug": result.task_slug},
            sort_keys=True))
    else:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status in {"ready", "ready_with_warnings",
        "manual_review_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
