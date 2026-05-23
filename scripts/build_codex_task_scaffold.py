from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_task_scaffold import (
    CodexTaskScaffoldRequest,
    build_codex_task_scaffold,
    write_prompt_artifact,
    write_scaffold_artifact,
)


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _list(base: dict[str, object], key: str, fallback: list[str]) -> tuple[str, ...]:
    value = base.get(key, fallback)
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    if isinstance(value, tuple):
        return tuple(str(v) for v in value)
    return tuple(fallback)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path)
    p.add_argument("--task-name")
    p.add_argument("--task-goal")
    p.add_argument("--subsystem-kind")
    p.add_argument("--prompt-mode", choices=("whole_system", "narrow_repair"), default="whole_system")
    p.add_argument("--current-chain-context", action="append", default=[])
    p.add_argument("--deliverable", action="append", default=[])
    p.add_argument("--new-module", action="append", default=[])
    p.add_argument("--new-cli", action="append", default=[])
    p.add_argument("--test-path", action="append", default=[])
    p.add_argument("--doc-path", action="append", default=[])
    p.add_argument("--capability-id")
    p.add_argument("--proof-bundle-artifact-kind")
    p.add_argument("--allowed-behavior", action="append", default=[])
    p.add_argument("--forbidden-behavior", action="append", default=[])
    p.add_argument("--validation-command", action="append", default=[])
    p.add_argument("--commit-title")
    p.add_argument("--output", type=Path)
    p.add_argument("--prompt-output", type=Path)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--emit-prompt", action="store_true")
    a = p.parse_args(argv)

    base: dict[str, object] = _load_json(a.input) if a.input else {}
    req = CodexTaskScaffoldRequest(
        task_name=str(base.get("task_name", a.task_name or "")),
        task_goal=str(base.get("task_goal", a.task_goal or "")),
        subsystem_kind=str(base.get("subsystem_kind", a.subsystem_kind or "")),
        prompt_mode=str(base.get("prompt_mode", a.prompt_mode)),
        current_chain_context=_list(base, "current_chain_context", a.current_chain_context),
        deliverables=_list(base, "deliverables", a.deliverable),
        new_module_path=_list(base, "new_module_path", a.new_module),
        new_cli_path=_list(base, "new_cli_path", a.new_cli),
        expected_test_paths=_list(base, "expected_test_paths", a.test_path),
        expected_doc_paths=_list(base, "expected_doc_paths", a.doc_path),
        capability_id=str(base.get("capability_id", a.capability_id or "")),
        proof_bundle_artifact_kind=str(base.get("proof_bundle_artifact_kind", a.proof_bundle_artifact_kind or "")),
        allowed_behaviors=_list(base, "allowed_behaviors", a.allowed_behavior),
        forbidden_behaviors=_list(base, "forbidden_behaviors", a.forbidden_behavior),
        validation_commands=_list(base, "validation_commands", a.validation_command),
        commit_title=str(base.get("commit_title", a.commit_title or "")),
    )
    result = build_codex_task_scaffold(req)
    if a.output:
        write_scaffold_artifact(result, a.output)
    if a.prompt_output:
        write_prompt_artifact(result, a.prompt_output)
    if a.summary:
        print(json.dumps({"status": result.status, "scaffold_id": result.scaffold.scaffold_id}, sort_keys=True))
    else:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if a.emit_prompt:
        print(result.scaffold.generated_prompt)
    return 0 if result.status in {"codex_task_scaffold_ready", "codex_task_scaffold_ready_with_warnings", "codex_task_scaffold_manual_review_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
