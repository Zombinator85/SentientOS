from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.no_legacy_skip


def test_semantic_lint_exception_is_limited_to_reviewed_front_door_contracts() -> None:
    source = (ROOT / "scripts/semantic_lint.sh").read_text(encoding="utf-8")
    expected = {
        "README.md",
        "one_pager.md",
        "WHAT_SENTIENTOS_IS_NOT.md",
        "NON_GOALS_AND_FREEZE.md",
        "docs/PUBLIC_LANGUAGE_BRIDGE.md",
        "docs/architecture/public_technical_overview.md",
        "docs/architecture/sentientos_project_thesis.md",
        "docs/architecture/sentientos_trajectory_and_missing_organs.md",
    }
    block = source.split("ARCHITECTURAL_BOUNDARY_DOCS=(", 1)[1].split(")", 1)[0]
    assert {line.strip().strip('"') for line in block.splitlines() if '"' in line} == expected
    assert 'is_architectural_boundary_doc "$file" && continue' in source


def test_semantic_rules_explain_mechanism_versus_architecture_distinction() -> None:
    rules = (ROOT / "SEMANTIC_REGRESSION_RULES.md").read_text(encoding="utf-8")
    assert "no engineered mechanism" in rules
    assert "architecturally impossible" in rules
    assert "does not extend to runtime code or ordinary documentation" in rules
