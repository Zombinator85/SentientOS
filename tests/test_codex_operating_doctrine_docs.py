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
    assert "two phases during the same implementation task" in agents
    assert "Do not defer post-commit/pr-metadata finalizer" in agents
    assert "do not run commit or `make_pr`" in agents
    assert "pr_metadata_guard_ready" in agents
    assert "BLOCKED_DO_NOT_IMPLEMENT" in agents
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
    assert "## Two-phase finalizer commands (required)" in whole
    assert "--phase pre-commit" in whole
    assert "--phase pr-metadata" in whole
    assert "before `make_pr`" in whole
    assert "pr_metadata_guard_ready" in whole
    assert "If bootstrap status is blocked, stop" in whole

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
    assert "Validation-only seal turns should not be necessary" in contract
    assert "must self-seal using both phases" in contract
    assert "Missing post-commit/pr-metadata finalizer" in contract
    assert "Do not defer post-commit sealing" in contract
    assert "BLOCKED_DO_NOT_IMPLEMENT" in contract
    assert "pr_metadata_guard_ready" in contract

    finalize = _read("docs/development/codex_finalize_landing.md")
    assert "Canonical two-phase command examples" in finalize
    assert "No-change validation-only example" in finalize
    assert "Anti-patterns" in finalize
    assert "partial finalizer usage" in finalize
    assert "codex_pr_metadata_guard.py verify" in finalize

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


def test_failure_taxonomy_and_prompt_compression_doctrine() -> None:
    agents = _read("AGENTS.md")
    rail = _read("docs/development/codex_landing_evidence_recovery_rail.md")
    roadmap = _read("docs/development/codex_open_work_roadmap_index.md")
    profile = _read("docs/development/codex_memory_chain_task_profile.md")
    contract = _read("docs/development/codex_validation_and_landing_contract.md")

    for label in [
        "implementation_failure",
        "pr_metadata_failure",
        "finalizer_stale_evidence_failure",
        "workspace_state_loss",
        "workspace_contamination_or_absence_gate_failure",
        "environment_or_dependency_noise",
        "graph_topology_discovery_failure",
        "lane_or_matrix_contract_failure",
        "prompt_bloat_or_repeated_law_failure",
    ]:
        assert label in rail

    for label in [
        "file_anchored_implementation",
        "topology_reconstruction_or_insertion_point_discovery",
        "doctrine_metadata_or_landing_repair",
        "local_node_readiness_planning",
        "federation_or_distributed_proof_topology",
    ]:
        assert label in rail

    for doc in [agents, rail, roadmap, profile]:
        assert "task-specific deltas" in doc
    assert "fresh-current/current-doctrine requirement" in rail
    assert "unique blockers or authority boundaries" in rail
    assert "bootstrap -> required validation -> pre-commit finalizer" in contract
    assert "Focused tests alone are insufficient" in contract
    assert "docs build when docs changed" in contract
    assert "targeted mypy when Python surfaces changed" in contract


def test_recovery_topology_and_local_node_notes_are_non_runtime() -> None:
    rail = _read("docs/development/codex_landing_evidence_recovery_rail.md")
    assert "same-workspace surgical recovery" in rail or "same-workspace recovery" in rail
    assert "no-files-found" in rail
    assert "canonical artifacts" in rail
    assert "Federation/Genesis Forge distributed coding labor is future proof-sharing" in rail
    assert "non-duplicative work-claim topology" in rail
    assert "claim semantics, proof exchange, artifact schema, and authority boundaries" in rail
    assert "does not implement routing, task execution, remote work dispatch, adoption, sync, merge, install, or execution behavior" in rail
    assert "Repository mainline state stays canonical" in rail
    assert "fresh local clone, clean baselines, dependency readiness, and local-node health checks" in rail

def test_context_hygiene_denial_phase_docs_are_validation_only() -> None:
    spine = _read("docs/architecture/context_hygiene_spine.md")
    contract = _read("docs/development/codex_validation_and_landing_contract.md")
    roadmap = _read("docs/development/codex_open_work_roadmap_index.md")

    for doc in (spine, contract):
        assert "Phase 97-103" in doc
        assert "validation" in doc.lower()
        assert "python scripts/verify_context_hygiene_prompt_boundaries.py" in doc
        assert "python -m scripts.run_tests -q tests/test_capability_registry.py tests/test_work_item_review_packet_matrix.py" in doc
        assert "provider invocation" in doc
        assert "prompt assembly" in doc
        assert "runtime authority" in doc
        assert "live `assemble_prompt(...)` behavior" in doc

    assert "Phase 97-103 context-hygiene denial-phase coverage is wired" in roadmap
    assert "tests/test_capability_registry.py" in spine
    assert "tests/test_work_item_review_packet_matrix.py" in spine
    assert "scripts/run_work_item_review_packet_matrix.py" in spine
    assert "sentientos/capability_registry.py" in spine

