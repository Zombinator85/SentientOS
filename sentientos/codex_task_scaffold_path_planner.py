from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

READY = {"ready", "ready_with_warnings", "manual_review_required"}
NONZERO = {"insufficient", "blocked", "failed"}
_COMMIT_TITLE_RE = re.compile(r"^\[codex:[a-z0-9-]+\]\s+.+$")
_SNAKE_RE = re.compile(r"[^a-z0-9]+")
_FORBIDDEN_RE = re.compile(r"(provider|openai|github|network|subprocess|shell|action\s*wing)", re.IGNORECASE)
_NEGATION_PREFIX_RE = re.compile(r"\b(do\s+not|don't|must\s+not|shall\s+not|never|no|without)\b", re.IGNORECASE)
_AFFIRMATIVE_BETWEEN_RE = re.compile(r"\b(use|call|access|invoke|spawn|execute|run|enable|allow)\b", re.IGNORECASE)
_DIRECT_NEGATED_ACTION_RE = re.compile(r"^\s*(?:(?:use|call|access|invoke|spawn|execute|run|enable|allow)\s+)?(?:the\s+)?$", re.IGNORECASE)
_PROHIBITION_SUFFIX_RE = re.compile(
    r"^\s*(?:apis?\b|calls?\b|access\b|execution\b|inference\b)?\s*"
    r"(?:is|are|must\s+remain|shall\s+remain)?\s*"
    r"(?:forbidden|prohibited|disabled|disallowed|not\s+allowed|must\s+not\s+be\s+used)\b",
    re.IGNORECASE,
)
_CLAUSE_BOUNDARY_RE = re.compile(r"[.;\n]+")
_REDUCTION_BEFORE_RE = re.compile(
    r"\b(remove|eliminate|disable|prohibit|restrict)\b[^.;\n]{0,80}$", re.IGNORECASE
)
_ANTI_REDUCTION_RE = re.compile(
    r"\b(?:remove|eliminate|disable)\s+(?:the\s+)?(?:restrictions?|prohibitions?|blocking|denials?)\s+(?:on|of|for)?\s*$",
    re.IGNORECASE,
)
_REDUCTION_AFTER_RE = re.compile(
    r"^.{0,80}\b(?:by\s+)?(?:removing|eliminating|disabling|deleting|prohibiting|restricting)\b",
    re.IGNORECASE,
)
_REPLACEMENT_RE = re.compile(r"\breplace\b(?P<source>.+?)\bwith\b(?P<target>.+)", re.IGNORECASE)
_LEXICAL_PROHIBITION_RE = re.compile(r"(?:\bnon[-\s]?$|\bno[-\s]?$)", re.IGNORECASE)
_LATER_AFFIRMATIVE_RE = re.compile(
    r"\b(?:then|but|and)\s+(?:\w+\s+){0,3}(?:use|call|access|invoke|spawn|execute|run|enable|allow)\b",
    re.IGNORECASE,
)
_COORDINATED_PROHIBITION_RE = re.compile(
    r"(?:\b(?:is|are)\s+(?:forbidden|prohibited|disabled|disallowed)\b|"
    r"\bmust\s+(?:remain\s+disabled|not\s+be\s+used)\b)\s*$",
    re.IGNORECASE,
)


class _AuthorityIntent(str, Enum):
    PROHIBITED = "prohibited"
    REDUCTION = "reduction"
    AFFIRMATIVE = "affirmative"
    AMBIGUOUS = "ambiguous"

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
    fixture_root: str
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


def _authority_intent(text: str, match: re.Match[str]) -> _AuthorityIntent:
    """Classify one authority-surface occurrence using only its local clause."""
    boundaries_before = tuple(_CLAUSE_BOUNDARY_RE.finditer(text, 0, match.start()))
    clause_start = boundaries_before[-1].end() if boundaries_before else 0
    boundary_after = _CLAUSE_BOUNDARY_RE.search(text, match.end())
    clause_end = boundary_after.start() if boundary_after else len(text)
    prefix = text[clause_start:match.start()]
    suffix = text[match.end():clause_end]

    if _ANTI_REDUCTION_RE.search(prefix):
        return _AuthorityIntent.AFFIRMATIVE

    replacement = _REPLACEMENT_RE.search(text[clause_start:clause_end])
    if replacement:
        occurrence = match.start() - clause_start
        with_offset = replacement.start("target")
        if occurrence >= with_offset:
            if _LEXICAL_PROHIBITION_RE.search(prefix):
                return _AuthorityIntent.PROHIBITED
            return _AuthorityIntent.AFFIRMATIVE
        if _LATER_AFFIRMATIVE_RE.search(suffix):
            return _AuthorityIntent.AFFIRMATIVE
        return _AuthorityIntent.REDUCTION

    if _LATER_AFFIRMATIVE_RE.search(suffix):
        return _AuthorityIntent.AFFIRMATIVE

    prohibited = bool(_LEXICAL_PROHIBITION_RE.search(prefix))
    if not prohibited:
        negations = tuple(_NEGATION_PREFIX_RE.finditer(prefix))
        if negations:
            negation = negations[-1]
            between = prefix[negation.end():]
            if negation.group(1).lower() in {"no", "without"}:
                prohibited = not _AFFIRMATIVE_BETWEEN_RE.search(between)
            else:
                prohibited = bool(_DIRECT_NEGATED_ACTION_RE.match(between))
    if _PROHIBITION_SUFFIX_RE.match(suffix[:64]) or (
        _COORDINATED_PROHIBITION_RE.search(suffix) and not _AFFIRMATIVE_BETWEEN_RE.search(suffix)
    ):
        prohibited = True
    if prohibited:
        return _AuthorityIntent.PROHIBITED
    if _REDUCTION_BEFORE_RE.search(prefix) or _REDUCTION_AFTER_RE.match(suffix):
        return _AuthorityIntent.REDUCTION
    if _AFFIRMATIVE_BETWEEN_RE.search(prefix) or re.search(
        r"^.{0,48}\b(?:use|call|access|invoke|spawn|execute|run|enable|allow)\b", suffix, re.IGNORECASE
    ):
        return _AuthorityIntent.AFFIRMATIVE
    return _AuthorityIntent.AMBIGUOUS


def _forbidden_authority_requested(text: str) -> bool:
    """Return true unless every authority occurrence is prohibited or reduced."""
    for match in _FORBIDDEN_RE.finditer(text):
        if _authority_intent(text, match) not in {_AuthorityIntent.PROHIBITED, _AuthorityIntent.REDUCTION}:
            return True
    return False


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
    fixture_root_default = f"tests/fixtures/{cap_default}/" if (request.subsystem_kind or request.preset_id) == "metadata_verification" and cap_default else ""
    commit_default = f"[codex:{scope}] {action} {slug.replace('_', ' ')}"

    module_path = _choose(request.new_module, module_default)
    cli_path = _choose(request.new_cli, cli_default)
    tests = request.test_path or (api_test_default, cli_test_default)
    api_test_path = tests[0]
    cli_test_path = tests[1] if len(tests) > 1 else cli_test_default
    dev_doc_path = _choose(request.doc_path, doc_default)
    commit_title = request.commit_title or commit_default

    for text in (request.task_name, request.task_goal, request.preset_id, request.subsystem_kind):
        if _forbidden_authority_requested(text):
            blockers.append("forbidden_authority_surface_requested")
            break

    for path in tuple(x for x in (module_path, cli_path, api_test_path, cli_test_path, dev_doc_path, proof_filename_default, fixture_root_default) if x):
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
    return PlannerOutput(status, tuple(sorted(set(warnings))), tuple(sorted(set(blockers))), slug, module_path, cli_path, api_test_path, cli_test_path, dev_doc_path, cap_default, proof_kind_default, proof_filename_default, fixture_root_default, commit_title)


def build_scaffold_request_payload(request: PlannerRequest, planned: PlannerOutput) -> dict[str, Any]:
    return {
        "task_name": request.task_name,
        "task_goal": request.task_goal,
        "subsystem_kind": request.subsystem_kind or request.preset_id,
        "new_module_path": [planned.module_path],
        "new_cli_path": [planned.cli_path],
        "expected_test_paths": [planned.api_test_path, planned.cli_test_path],
        "expected_doc_paths": [planned.dev_doc_path],
        "expected_fixture_roots": [planned.fixture_root] if planned.fixture_root else [],
        "capability_id": planned.capability_id,
        "proof_bundle_artifact_kind": planned.proof_bundle_artifact_kind,
        "commit_title": planned.commit_title,
    }


def write_json(path: PurePosixPath | str, payload: dict[str, Any]) -> None:
    from pathlib import Path
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
