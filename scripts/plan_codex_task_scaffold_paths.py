from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_task_scaffold_path_planner import (
    NONZERO,
    PlannerRequest,
    build_scaffold_request_payload,
    plan_codex_task_scaffold_paths,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--task-name", required=True)
    p.add_argument("--task-goal", default="")
    p.add_argument("--preset-id", default="")
    p.add_argument("--subsystem-kind", default="")
    p.add_argument("--commit-scope", default="developer")
    p.add_argument("--output", type=Path)
    p.add_argument("--scaffold-request-output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--new-module", action="append", default=[])
    p.add_argument("--new-cli", action="append", default=[])
    p.add_argument("--test-path", action="append", default=[])
    p.add_argument("--doc-path", action="append", default=[])
    p.add_argument("--capability-id", default="")
    p.add_argument("--proof-bundle-artifact-kind", default="")
    p.add_argument("--commit-title", default="")
    a = p.parse_args(argv)

    req = PlannerRequest(
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
    )
    out = plan_codex_task_scaffold_paths(req)
    payload = out.to_dict()
    if a.output:
        write_json(a.output, payload)
    if a.scaffold_request_output:
        write_json(a.scaffold_request_output, build_scaffold_request_payload(req, out))
    if a.summary:
        print(json.dumps({"status": out.status, "task_slug": out.task_slug}, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if out.status in NONZERO else 0


if __name__ == "__main__":
    raise SystemExit(main())
