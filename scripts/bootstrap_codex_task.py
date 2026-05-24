from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_task_bootstrapper import CodexTaskBootstrapRequest, bootstrap_codex_task, write_bootstrap_artifacts


NONZERO = {"insufficient", "blocked", "failed"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--task-name", required=True)
    p.add_argument("--task-goal", required=True)
    p.add_argument("--preset-id", default="")
    p.add_argument("--subsystem-kind", default="")
    p.add_argument("--commit-scope", default="developer")
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--summary-output", type=Path)
    p.add_argument("--plan-output", type=Path)
    p.add_argument("--scaffold-output", type=Path)
    p.add_argument("--prompt-output", type=Path)
    p.add_argument("--verifier-output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--emit-prompt", action="store_true")
    p.add_argument("--new-module", action="append", default=[])
    p.add_argument("--new-cli", action="append", default=[])
    p.add_argument("--test-path", action="append", default=[])
    p.add_argument("--doc-path", action="append", default=[])
    p.add_argument("--capability-id", default="")
    p.add_argument("--proof-bundle-artifact-kind", default="")
    p.add_argument("--commit-title", default="")
    a = p.parse_args(argv)

    result = bootstrap_codex_task(CodexTaskBootstrapRequest(
        task_name=a.task_name,
        task_goal=a.task_goal,
        preset_id=a.preset_id,
        subsystem_kind=a.subsystem_kind,
        commit_scope=a.commit_scope,
        new_module=tuple(a.new_module),
        new_cli=tuple(a.new_cli),
        test_path=tuple(a.test_path),
        doc_path=tuple(a.doc_path),
        capability_id=a.capability_id,
        proof_bundle_artifact_kind=a.proof_bundle_artifact_kind,
        commit_title=a.commit_title,
    ))

    out_dir = a.output_dir
    summary_output = a.summary_output or (out_dir / "bootstrap.summary.json" if out_dir else None)
    plan_output = a.plan_output or (out_dir / "bootstrap.plan.json" if out_dir else None)
    scaffold_output = a.scaffold_output or (out_dir / "bootstrap.scaffold.json" if out_dir else None)
    prompt_output = a.prompt_output or (out_dir / "bootstrap.prompt.txt" if out_dir else None)
    verifier_output = a.verifier_output or (out_dir / "bootstrap.verifier.json" if out_dir else None)
    if any([summary_output, plan_output, scaffold_output, prompt_output, verifier_output]):
        write_bootstrap_artifacts(result, summary_output=summary_output, plan_output=plan_output, scaffold_output=scaffold_output, prompt_output=prompt_output, verifier_output=verifier_output)

    payload = result.to_dict()
    if a.summary:
        print(json.dumps({"status": result.status, "task_slug": result.planner_result_summary.get("task_slug", "")}, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    if a.emit_prompt:
        print(result.generated_prompt_text)
    return 1 if result.status in NONZERO else 0


if __name__ == "__main__":
    raise SystemExit(main())
