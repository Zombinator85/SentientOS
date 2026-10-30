from __future__ import annotations

import argparse
import json

from sentientos.codex_task_scaffold_path_planner import (
    PlannerRequest,
    plan_codex_task_scaffold_paths,
)


TASK_NAME = "Summarize model-bound epistemic qualification reports"
TASK_GOAL = (
    "Add a stateless read-only summarizer for existing epistemic qualification "
    "reports. Verify report and per-sample execution-binding digests, group each "
    "before/after sample by exact case commitment and measured model/artifact/"
    "active-identity/generation-config/evaluator identity, preserve pass/fail/"
    "insufficient outcomes without inference, and state that fixture or supplied "
    "reports do not establish real-model qualification. No profile registry, "
    "persistent storage, runtime mutation, provider calls, or authority changes."
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
        commit_title="[codex:experiments] summarize model-bound epistemic reports",
        new_module=("sentientos/epistemic_qualification_cohort.py",),
        new_cli=("scripts/summarize_epistemic_qualification_cohort.py",),
        test_path=(
            "tests/test_epistemic_qualification_cohort.py",
            "tests/test_plan_summarize_model_bound_epistemic_reports_script.py",
        ),
        doc_path=("docs/development/epistemic_qualification_cohort.md",),
        capability_id="epistemic_qualification_cohort",
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
