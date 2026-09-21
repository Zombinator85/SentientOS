from __future__ import annotations

import re
from pathlib import Path

import pytest

from sentientos.capability_registry import build_default_capability_registry

pytestmark = pytest.mark.no_legacy_skip

DOCS = {
    name: Path(path).read_text(encoding="utf-8")
    for name, path in {
        "readme": "README.md",
        "one_pager": "one_pager.md",
        "overview": "docs/architecture/public_technical_overview.md",
        "thesis": "docs/architecture/sentientos_project_thesis.md",
        "trajectory": "docs/architecture/sentientos_trajectory_and_missing_organs.md",
        "not": "WHAT_SENTIENTOS_IS_NOT.md",
        "doctrine": "DOCTRINE.md",
        "glossary": "SEMANTIC_GLOSSARY.md",
        "usage": "docs/USAGE.md",
        "docket": "docs/architecture/forward_documentation_reconciliation_docket.md",
    }.items()
}
PUBLIC = "\n".join(DOCS.values())
OVERVIEW = DOCS["overview"]
RECORDS = build_default_capability_registry().by_id()


def normalized(text: str) -> str:
    return " ".join(text.lower().split())


def test_front_door_defines_system_and_model_boundary() -> None:
    readme = normalized(DOCS["readme"])
    assert "persistent, model-agnostic runtime" in readme
    assert "model identity is not system identity" in readme
    assert "model-agnostic means" in readme
    assert "not a claim that this system is conscious or sentient today" in readme


def test_frozen_architectural_invariants_are_public() -> None:
    for invariant in (
        "memory != current truth",
        "proposal != authorization",
        "repository absorption != runtime adoption",
        "capability definition != grant",
        "grant != operational feasibility",
        "operational feasibility != admission",
        "admission != execution",
    ):
        assert invariant in PUBLIC


def test_world_state_is_evidence_bound_and_read_only() -> None:
    overview = normalized(OVERVIEW)
    assert "world-state is a deterministic, digest-bound, read-only projection" in overview
    assert all(term in overview for term in ("provenance", "freshness", "staleness", "conflicts"))
    assert "perfect self-knowledge or philosophical omniscience" in overview


def test_memory_generations_are_not_flattened() -> None:
    overview = normalized(OVERVIEW)
    assert "canonical governed conversation memory is live" in overview
    assert "legacy memory managers" in overview
    assert "selective distillation machinery" in overview
    assert "live-memory planning/readiness/interlocks" in overview
    record = RECORDS["selective_memory_distillation_contract"]
    assert (record.status, record.authority_level) == ("implemented", "metadata_verification_only")


def test_perception_statuses_agree_with_registry() -> None:
    for capability in ("perception_audio", "perception_screen", "perception_vision"):
        assert RECORDS[capability].status == "partial"
        assert capability in OVERVIEW
    assert "embodiment_ingress.py" in OVERVIEW
    assert "host_resource_runtime.py" in OVERVIEW


def test_host_observation_is_not_blanket_control() -> None:
    overview = normalized(OVERVIEW)
    assert "phase-one host-resource operation is read-only" in overview
    assert "do not amount to universal computer control" in overview
    assert "observation != blanket host control" in overview


def test_external_https_is_real_but_not_default_active() -> None:
    overview = normalized(OVERVIEW)
    assert "external-model execution is implemented, not hypothetical" in overview
    assert "exact https transport" in overview
    assert "unavailable by default" in overview
    assert "no provider is contacted automatically" in overview
    assert "untrusted_external_data" in overview
    assert Path("sentientos/external_model_https_transport.py").is_file()
    assert Path("sentientos/external_model_execution_custody.py").is_file()


def test_maintenance_replacement_is_current_and_bounded() -> None:
    record = RECORDS["maintenance_resident_runtime_adoption"]
    assert (record.status, record.authority_level) == ("implemented", "bounded-orchestrator")
    overview = normalized(OVERVIEW)
    assert "current / implemented but bounded" in overview
    assert "replace the resident posix `sentientosd` process image" in overview
    assert "not unrestricted recursive self-improvement" in overview


def test_parent_supervision_and_generic_restart_remain_unavailable() -> None:
    parent = RECORDS["maintenance_resident_parent_supervision"]
    assert (parent.status, parent.authority_level) == ("scaffolded", "eligibility_only")
    assert {"stable parent runtime implementation", "process-death recovery"} <= set(parent.deferred_surfaces)
    assert "SCAFFOLDED / ELIGIBILITY-ONLY" in OVERVIEW
    assert "No stable parent runtime is implemented" in OVERVIEW
    assert "No child watcher/restart loop" in OVERVIEW
    restart = RECORDS["real_service_restart"]
    assert (restart.status, restart.authority_level) == ("blocked", "none")
    assert "`real_service_restart` remains **BLOCKED / none**" in OVERVIEW


def test_formal_and_reference_monitor_claims_are_scoped() -> None:
    public = normalized(PUBLIC)
    assert "whole python system is not formally verified" in public or "sentientos is not wholly formally verified" in public
    assert "reference-monitor-like" in public
    assert "universal mediation" in public or "complete mediation" in public
    prohibited = (
        r"\bsentientos is formally verified\b",
        r"\bfully autonomous\b",
    )
    assert not any(re.search(pattern, public) for pattern in prohibited)


def test_federation_and_multi_agent_are_not_default_claims() -> None:
    public = normalized(PUBLIC)
    assert "supported default production wan synchronization deployment" in public
    assert "not primarily a multi-agent orchestrator" in public


def test_usage_accounts_for_packaged_and_module_entrypoints() -> None:
    usage = DOCS["usage"]
    assert "24 console scripts and seven `python -m` launch forms" in usage
    for section in (
        "Primary supported launch paths",
        "Operator and administrative tools",
        "Specialist and reviewer tools",
        "Compatibility and cultural aliases",
        "Development and testing",
    ):
        assert f"## {section}" in usage
    assert "prefer `sentientos-procedure`" in usage
    assert "prefer `sentientos-governance-ui`" in usage


def test_document_hierarchy_and_atlas_navigation() -> None:
    nav = Path("mkdocs.yml").read_text(encoding="utf-8")
    assert nav.index("One Pager:") < nav.index("Current Architecture:")
    assert "Current-System Atlas: docs/architecture/current_repository_system_atlas.md" in nav
    assert "Reviewer Readiness: docs/architecture/reviewer_release_readiness_index.md" in nav
    assert "current_repository_system_atlas.md" in DOCS["readme"]


def test_docket_closes_all_audited_findings() -> None:
    docket = DOCS["docket"]
    assert "All **32 of 32** audited claims" in docket
    assert "No high-priority finding remains unresolved" in docket
    assert "deferred_due_to_unknown_evidence" not in docket
    assert docket.count("**resolved**") + docket.count("**intentionally_retained_with_qualification**") == 32


def test_atlas_snapshots_remain_tracked_evidence() -> None:
    assert Path("architecture/current_repository_system_atlas.json").is_file()
    assert Path("docs/architecture/current_repository_system_atlas.md").is_file()


def test_established_terminology_qualifications_remain_available() -> None:
    terms = Path("docs/architecture/relationship_to_existing_terminology.md").read_text(encoding="utf-8")
    assert "No unimplemented protocol conformance is claimed" in terms
    assert "Current world-state evidence is not a predictive world model" in terms
    assert "Autonomy is not authority" in terms
    assert "not unrestricted recursive self-improvement" in terms
