from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_agents_is_compact_map_and_moved_doctrine_links_resolve() -> None:
    agents = _read("AGENTS.md")
    assert len(agents.splitlines()) <= 250
    for marker in ["operator", "safe shutdown", "Codex hot path", "python -m scripts.run_tests", "provider", "network", "host actuation", "pr_metadata_guard_ready", "pr_body_binding_ready"]:
        assert marker in agents
    links = re.findall(r"\[[^]]+\]\(([^)]+)\)", agents)
    assert links
    for link in links:
        assert (ROOT / link).exists(), link
    archive = _read("docs/AGENTS_DOCTRINE_ARCHIVE.md")
    for doctrine in ["Cathedral Blessing", "Agent Definition and Taxonomy", "Privilege Contracts", "Federation & World Integration"]:
        assert doctrine in archive


def test_stable_law_has_one_policy_and_one_command_reference() -> None:
    agents = _read("AGENTS.md")
    template = _read("docs/development/codex_whole_system_task_template.md")
    assert "policy source" in agents
    assert "executable commands" in agents
    assert "do not duplicate their command blocks" in template
    assert "--phase pre-commit" not in template
    assert "--phase pr-metadata" not in template
    assert "## Objective" in template
    assert "## Verified current gap" in template
    assert "## Observable acceptance proof" in template


def test_active_roadmap_is_current_and_archive_is_linked() -> None:
    roadmap = _read("docs/development/codex_open_work_roadmap_index.md")
    assert "697febe" in roadmap
    assert "operator-confirmed diagnostic runtime" in roadmap.lower()
    assert "behavioral-proof gap" in roadmap
    assert "codex_open_work_roadmap_archive_2026-07.md" in roadmap
    assert len(roadmap.splitlines()) < 100


def test_acceptance_contract_rejects_aggregate_only_proof() -> None:
    contract = _read("docs/development/codex_validation_and_landing_contract.md")
    for marker in ["sentientos.task_acceptance:v1", "selected_node_ids", "node_outcomes", "setup-only", "--task-acceptance-manifest", "aggregate counts"]:
        assert marker in contract
