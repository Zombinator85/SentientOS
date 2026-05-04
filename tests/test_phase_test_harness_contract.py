from __future__ import annotations

import ast
from pathlib import Path

from tests.legacy_policy import is_legacy_candidate

PHASE_TEST_GLOB = "test_phase*.py"
APPROVED_EMPTY_PHASE_MODULES: set[str] = set()


class _ModuleInspection(ast.NodeVisitor):
    def __init__(self) -> None:
        self.module_skip_reasons: list[str] = []
        self.test_functions = 0

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "pytestmark":
                reason = _extract_module_skip_reason(node.value)
                if reason is not None:
                    self.module_skip_reasons.append(reason)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        target = node.target
        if isinstance(target, ast.Name) and target.id == "pytestmark" and node.value is not None:
            reason = _extract_module_skip_reason(node.value)
            if reason is not None:
                self.module_skip_reasons.append(reason)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        if node.name.startswith("test_"):
            self.test_functions += 1
        self.generic_visit(node)


def _extract_module_skip_reason(value: ast.AST) -> str | None:
    nodes = [value]
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        nodes = list(value.elts)
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "skip":
            continue
        for kw in node.keywords:
            if kw.arg == "reason" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
        return ""
    return None


def _phase_test_paths() -> list[Path]:
    return sorted(Path("tests").glob(PHASE_TEST_GLOB))


def _module_name(path: Path) -> str:
    return ".".join(path.with_suffix("").parts)


def test_phase_files_are_not_legacy_candidates_by_default() -> None:
    for path in _phase_test_paths():
        assert is_legacy_candidate(
            module_name=_module_name(path),
            path_str=str(path),
            test_name="test_contract_probe",
            keywords={},
            allowed_modules=set(),
        ) is False, f"{path} unexpectedly considered legacy candidate"


def test_phase_modules_have_tests_or_approved_module_skip_reason() -> None:
    for path in _phase_test_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        inspect = _ModuleInspection()
        inspect.visit(tree)

        if inspect.module_skip_reasons:
            for reason in inspect.module_skip_reasons:
                assert reason.strip(), f"{path} has module-level skip without explicit reason"
                assert "phase" in reason.lower() or "legacy" in reason.lower() or "approved" in reason.lower(), (
                    f"{path} skip reason must be explicit/searchable: {reason!r}"
                )
            continue

        assert inspect.test_functions > 0, f"{path} has no test_* functions"
        assert str(path) not in APPROVED_EMPTY_PHASE_MODULES, (
            f"{path} listed as approved empty but has no module-level skip"
        )


def test_phase45_through_phase59_modules_present_and_covered() -> None:
    expected = {
        "tests/test_phase45_ingress_gated_effects.py",
        "tests/test_phase46_ingress_gated_retention.py",
        "tests/test_phase48_embodied_proposals.py",
        "tests/test_phase49_embodied_proposal_visibility.py",
        "tests/test_phase50_embodied_proposal_review_receipts.py",
        "tests/test_phase56_evidence_stability_spine.py",
        "tests/test_phase57_evidence_diagnostic_memory_guard.py",
        "tests/test_phase58_truth_log_fed_preflight.py",
        "tests/test_phase59_research_response_gate.py",
    }
    discovered = {str(p) for p in _phase_test_paths()}
    missing = expected - discovered
    assert not missing, f"missing expected phase modules: {sorted(missing)}"
