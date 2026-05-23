from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

READY = {"ready", "ready_with_warnings", "manual_review_required"}
NONZERO = {"insufficient", "blocked", "failed"}
_COMMIT_TITLE_RE = re.compile(r"^\[codex:[a-z0-9-]+\]\s+.+$")
_SNAKE_RE = re.compile(r"[^a-z0-9]+")
_FORBIDDEN_RE = re.compile(r"(provider|openai|github|network|subprocess|shell|action\s*wing)", re.IGNORECASE)

@dataclass(frozen=True)
class PlannerRequest:
    task_name: str
    task_goal: str = ""
    preset_id: str = ""
    subsystem_kind: str = ""
    domain_prefix: str = ""
    action_verb: str = "add"
    package_root: str = "sentientos"
    script_prefix: str = "plan"
    commit_scope: str = "developer"
    new_module: tuple[str, ...] = ()
    new_cli: tuple[str, ...] = ()
    test_path: tuple[str, ...] = ()
    doc_path: tuple[str, ...] = ()
    capability_id: str = ""
    proof_bundle_artifact_kind: str = ""
    commit_title: str = ""


@dataclass(frozen=True)
class PlannerOutput:
    status: str
    warning_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    task_slug: str
    module_path: str
    cli_path: str
    api_test_path: str
    cli_test_path: str
    dev_doc_path: str
    capability_id: str
    proof_bundle_artifact_kind: str
    proof_bundle_filename: str
    commit_title: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _snake(text: str) -> str:
    compact = _SNAKE_RE.sub("_", text.strip().lower()).strip("_")
    return compact or "task"


def _bad_path(path: str) -> bool:
    return path.startswith("/") or ".." in PurePosixPath(path).parts or any(ch in path for ch in [";", "|", "&", "`", "$", "<", ">"])


def _ensure_root(path: str) -> bool:
    return path.startswith(("sentientos/", "scripts/", "tests/", "docs/", "artifacts/"))


def _choose(first: tuple[str, ...], default: str) -> str:
    return first[0] if first else default


def plan_codex_task_scaffold_paths(request: PlannerRequest) -> PlannerOutput:
    warnings: list[str] = []
    blockers: list[str] = []
    slug = _snake(request.task_name)
    scope = _snake(request.commit_scope) or "developer"
    action = _snake(request.action_verb) or "add"
    module_default = f"{request.package_root.strip('/')}/{slug}.py"
    cli_default = f"scripts/{request.script_prefix}_{slug}.py"
    api_test_default = f"tests/test_{slug}.py"
    cli_test_default = f"tests/test_{request.script_prefix}_{slug}_script.py"
    doc_default = f"docs/development/{slug}.md"
    cap_default = _snake(request.capability_id or slug)
    proof_kind_default = _snake(request.proof_bundle_artifact_kind or f"{cap_default}_capability")
    proof_filename_default = f"artifacts/proof_bundles/{proof_kind_default}.json"
    commit_default = f"[codex:{scope}] {action} {slug.replace('_', ' ')}"

    module_path = _choose(request.new_module, module_default)
    cli_path = _choose(request.new_cli, cli_default)
    tests = request.test_path or (api_test_default, cli_test_default)
    api_test_path = tests[0]
    cli_test_path = tests[1] if len(tests) > 1 else cli_test_default
    dev_doc_path = _choose(request.doc_path, doc_default)
    commit_title = request.commit_title or commit_default

    for text in (request.task_name, request.task_goal, request.preset_id, request.subsystem_kind):
        if _FORBIDDEN_RE.search(text):
            blockers.append("forbidden_authority_surface_requested")
            break

    for path in (module_path, cli_path, api_test_path, cli_test_path, dev_doc_path, proof_filename_default):
        if _bad_path(path):
            blockers.append("path_traversal_or_metacharacters")
            break
        if not _ensure_root(path):
            blockers.append("path_outside_allowed_roots")
            break

    if not _COMMIT_TITLE_RE.match(commit_title):
        warnings.append("nonconforming_commit_title")

    status = "ready"
    if blockers:
        status = "blocked"
    elif warnings:
        status = "ready_with_warnings"
    return PlannerOutput(status, tuple(sorted(set(warnings))), tuple(sorted(set(blockers))), slug, module_path, cli_path, api_test_path, cli_test_path, dev_doc_path, cap_default, proof_kind_default, proof_filename_default, commit_title)


def build_scaffold_request_payload(request: PlannerRequest, planned: PlannerOutput) -> dict[str, Any]:
    return {
        "task_name": request.task_name,
        "task_goal": request.task_goal,
        "subsystem_kind": request.subsystem_kind or request.preset_id,
        "new_module_path": [planned.module_path],
        "new_cli_path": [planned.cli_path],
        "expected_test_paths": [planned.api_test_path, planned.cli_test_path],
        "expected_doc_paths": [planned.dev_doc_path],
        "capability_id": planned.capability_id,
        "proof_bundle_artifact_kind": planned.proof_bundle_artifact_kind,
        "commit_title": planned.commit_title,
    }


def write_json(path: PurePosixPath | str, payload: dict[str, Any]) -> None:
    from pathlib import Path
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
