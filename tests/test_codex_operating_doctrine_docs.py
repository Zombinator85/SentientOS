from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_agents_mentions_whole_system_doctrine_and_links() -> None:
    agents = _read("AGENTS.md")
    assert "Human turnaround bandwidth is scarce" in agents
    assert "complete bounded subsystem" in agents
    assert "Tiny diffs are exceptional" in agents
    assert "full matrix not run" in agents
    assert "after the final task-caused code/doc/test change" in agents
    assert "No post-landing stabilization churn" in agents
    assert "required validation lane failures are task-owned until proven otherwise" in agents
    assert "If you want, I can run the full matrix now" in agents
    assert "proof-bundle" in agents
    assert "capability registry" in agents
    for path in [
        "docs/development/codex_whole_system_task_template.md",
        "docs/development/codex_narrow_repair_task_template.md",
        "docs/development/codex_validation_and_landing_contract.md",
        "docs/development/codex_capability_landing_checklist.md",
    ]:
        assert path in agents


def test_templates_exist_and_have_required_sections() -> None:
    whole = _read("docs/development/codex_whole_system_task_template.md")
    for section in [
        "## Goal",
        "## Why this is a system task",
        "## Context",
        "## Boundaries",
        "## Inputs",
        "## Outputs",
        "## Public API/module",
        "## CLI",
        "## Artifacts",
        "## Capability/proof surfaces when relevant",
        "## Matrix integration",
        "## Docs",
        "## Tests",
        "## Safety constraints",
        "## Validation commands",
        "## Failure handling",
        "## Done when",
        "## Final report format",
    ]:
        assert section in whole
    assert "Think in systems." in whole
    assert "Do not return piddly diffs" in whole
    assert "After the last task-caused code/doc/test change" in whole
    assert "Do not create PR metadata" in whole
    assert "required lane failures" in whole.lower()

    narrow = _read("docs/development/codex_narrow_repair_task_template.md")
    assert "Narrow repairs are exceptional" in narrow
    assert "must not be used to defer task-caused subsystem fallout" in narrow
    assert "exact command" in narrow.lower() or "exact failure" in narrow.lower()


def test_validation_contract_and_reviewer_docs_discoverability() -> None:
    contract = _read("docs/development/codex_validation_and_landing_contract.md")
    assert "continue running remaining feasible commands" in contract
    assert "failure as one of" in contract
    assert "Feature exists but full matrix not run" in contract
    assert "Required order is strict" in contract
    assert "1. Make the final task-caused code/doc/test change." in contract
    assert "2. Run the full relevant validation matrix" in contract
    assert "3. Only then produce final report and PR metadata." in contract
    assert "If you want, I can run the full matrix now" in contract
    assert "Required-lane repair loop" in contract

    checklist = _read("docs/development/codex_capability_landing_checklist.md")
    for marker in ["capability category", "authority level", "proof bundle", "readiness/index", "matrix runner", "targeted mypy", "docs link/index coverage"]:
        assert marker in checklist

    quick = _read("docs/REVIEWER_QUICKSTART.md")
    index = _read("docs/architecture/reviewer_release_readiness_index.md")
    for doc in [
        "docs/development/codex_whole_system_task_template.md",
        "docs/development/codex_narrow_repair_task_template.md",
        "docs/development/codex_validation_and_landing_contract.md",
        "docs/development/codex_capability_landing_checklist.md",
        "scripts/run_work_item_review_packet_matrix.py",
    ]:
        assert doc in quick or doc.replace("docs/", "") in quick
        assert doc in index
