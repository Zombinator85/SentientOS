from __future__ import annotations

import argparse
import json

from sentientos.codex_task_scaffold_path_planner import (
    PlannerRequest,
    plan_codex_task_scaffold_paths,
)


TASK_NAME = "Epistemic task-scope evidence window series"
TASK_GOAL = (
    "Compose existing persistent epistemic revision and interruption scoring "
    "with an exact task target and time-window binding. Detect stale or "
    "wrong-target source use after context interruption while checking actual "
    "answers, evidence delivery, and citations. Preserve incomplete, incorrect, "
    "and out-of-scope outcomes."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=TASK_GOAL)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    result = plan_codex_task_scaffold_paths(PlannerRequest(
        task_name=TASK_NAME,
        task_goal=TASK_GOAL,
        subsystem_kind="experiment_composer",
        commit_scope="experiments",
        commit_title="[codex:experiments] preserve epistemic task scope",
        new_module=("sentientos/epistemic_revision_task_scope_series.py",),
        new_cli=("scripts/plan_epistemic_revision_task_scope_series.py",),
        test_path=(
            "tests/test_epistemic_revision_task_scope_series.py",
            "tests/test_plan_epistemic_revision_task_scope_script.py",
        ),
        doc_path=("docs/development/epistemic_revision_task_scope_series.md",),
        capability_id="epistemic_revision_task_scope_series",
    ))
    if args.summary:
        print(json.dumps({"status": result.status, "task_slug": result.task_slug},
            sort_keys=True))
    else:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status in {
        "ready", "ready_with_warnings", "manual_review_required",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
