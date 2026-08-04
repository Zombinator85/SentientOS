from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_legacy_skip


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/architecture/host_local_diagnostic_lifecycle_reviewer_guide.md"
OVERVIEW = ROOT / "docs/architecture/public_technical_overview.md"
INDEX = ROOT / "docs/architecture/reviewer_release_readiness_index.md"
ROADMAP = ROOT / "docs/development/codex_open_work_roadmap_index.md"


def _text(path: Path) -> str:
    assert path.is_file(), f"required reviewer surface is missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _repo_python_paths(text: str) -> set[str]:
    return set(re.findall(r"(?<![\w/])(?:sentientos|scripts|tests)/[a-zA-Z0-9_./-]+\.py", text))


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(_text(path), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")}


def test_reviewer_guide_maps_complete_diagnostic_lifecycle() -> None:
    guide = _text(GUIDE)
    for heading in (
        "Scope and non-authority boundary",
        "Complete lifecycle map",
        "Operator workflow",
        "Custody and lifecycle transitions",
        "Failure semantics",
        "Reviewer proof map",
    ):
        assert f"## {heading}" in guide, f"reviewer guide is missing section: {heading}"
    for stage in (
        "Host-local diagnostic execution source",
        "Host-local diagnostic execution |",
        "Host-local diagnostic rollback",
        "Host-local diagnostic lifecycle closure",
    ):
        assert stage in guide, f"reviewer guide is missing lifecycle stage: {stage}"


def test_reviewer_guide_referenced_paths_and_commands_exist() -> None:
    guide = _text(GUIDE)
    paths = _repo_python_paths(guide)
    assert paths, "reviewer guide did not expose any repository Python proof paths"
    missing = sorted(path for path in paths if not (ROOT / path).is_file())
    assert not missing, f"reviewer guide references missing repository files: {missing}"

    closure_script = _text(ROOT / "scripts/build_host_local_diagnostic_lifecycle_closure.py")
    implemented = set(re.findall(r'add_parser\("([a-z-]+)"\)', closure_script))
    documented = {command for command in ("build", "validate", "latest-summary") if re.search(rf"\b{re.escape(command)}\b", guide)}
    assert documented == implemented == {"build", "validate", "latest-summary"}, (
        f"closure CLI mismatch: documented={sorted(documented)}, implemented={sorted(implemented)}"
    )


def test_reviewer_guide_named_pytest_nodes_exist() -> None:
    guide = _text(GUIDE)
    nodes = re.findall(r"`(tests/[a-zA-Z0-9_./-]+\.py::test_[a-zA-Z0-9_]+)`", guide)
    assert len(nodes) >= 8, "reviewer guide must name the representative behavioral proof nodes"
    failures: list[str] = []
    for node in nodes:
        path_text, function = node.split("::", 1)
        path = ROOT / path_text
        if not path.is_file():
            failures.append(f"missing test file: {path_text}")
        elif function not in _test_functions(path):
            failures.append(f"missing test function: {node}")
    assert not failures, "reviewer guide names unresolved pytest nodes: " + "; ".join(failures)


def test_reviewer_guide_preserves_authority_and_mutation_boundaries() -> None:
    guide = _text(GUIDE)
    required = (
        "Admission evidence is not execution authority",
        "Closure packets are historical evidence only",
        "integrity binding, not authorship or external authenticity",
        "The effect mutation boundary is exactly the six runtime-owned files",
        "The rollback mutation boundary is exactly deletion of `sentientos_local_diagnostic_effect.json`",
        "no sibling or other runtime-owned file is changed",
        "No guide, receipt, packet, test, or reviewer result grants provider, network, federation-adoption,",
        "broader host-effect, control-plane, or live-memory authority",
    )
    missing = [statement for statement in required if statement not in guide]
    assert not missing, f"reviewer guide weakened required authority or mutation wording: {missing}"
    assert "grants provider authority" not in guide.lower()
    assert "grants network authority" not in guide.lower()
    assert "grants broad host-effect authority" not in guide.lower()
    assert "grants federation adoption" not in guide.lower()
    assert "grants live-memory authority" not in guide.lower()


def test_public_overview_and_release_index_link_reviewer_guide() -> None:
    link = "host_local_diagnostic_lifecycle_reviewer_guide.md"
    overview = _text(OVERVIEW)
    index = _text(INDEX)
    assert link in overview, "public technical overview does not link the diagnostic lifecycle reviewer guide"
    assert "## Bounded diagnostic execution lifecycle" in overview
    assert link in index, "reviewer release-readiness index does not link the diagnostic lifecycle reviewer guide"
    for surface in (
        "host_local_diagnostic_execution_source_runtime.py",
        "host_local_diagnostic_execution_runtime.py",
        "host_local_diagnostic_rollback_runtime.py",
        "host_local_diagnostic_lifecycle_closure.py",
    ):
        assert surface in index, f"release-readiness index is missing proof surface: {surface}"


def test_active_roadmap_matches_current_main_and_implemented_posture() -> None:
    roadmap = _text(ROADMAP)
    assert "mainline `f6dbf1c`" in roadmap, "active roadmap current-main marker is not f6dbf1c"
    for posture in ("staged-copy validation", "genuine pre-flock independently spawned-process waiter proof", "kernel lock release across abrupt death", "packet-root-and-descendant-preserving pointer recovery", "reviewer path now consolidates"):
        assert posture in roadmap, f"active roadmap is missing implemented diagnostic posture: {posture}"
    assert "## Available next work" in roadmap
