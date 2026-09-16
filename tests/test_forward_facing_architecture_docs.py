from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.capability_registry import build_default_capability_registry

pytestmark = pytest.mark.no_legacy_skip

README = Path("README.md").read_text(encoding="utf-8")
OVERVIEW = Path("docs/architecture/public_technical_overview.md").read_text(encoding="utf-8")
TERMS = Path("docs/architecture/relationship_to_existing_terminology.md").read_text(encoding="utf-8")
NAV = Path("mkdocs.yml").read_text(encoding="utf-8")
RECORDS = build_default_capability_registry().by_id()


def prose(text: str) -> str:
    return " ".join(text.split())


def test_readme_system_vs_model_lifecycle() -> None:
    assert "SentientOS is not identical to its currently active inference model" in README
    assert "replaceable cognitive machinery" in README
    assert "System lifecycle" in README and "Inference lifecycle" in README


def test_public_overview_current_system_anatomy() -> None:
    assert "persistent SentientOS environment" in OVERVIEW
    for organ in ("model serving", "memory / distillation", "Household Presence", "world-state", "maintenance / software evolution"):
        assert organ in OVERVIEW


def test_perception_embodiment_is_source_backed() -> None:
    for capability in ("perception_audio", "perception_screen", "perception_vision"):
        assert RECORDS[capability].status == "partial"
        assert capability in OVERVIEW
    assert "embodiment_ingress.py" in OVERVIEW and "host_resource_runtime.py" in OVERVIEW


def test_household_presence_degree_of_closure_is_source_backed() -> None:
    assert "CURRENT / IMPLEMENTED POLICY AND METADATA CUSTODY; LIVE CAPTURE DEFERRED" in OVERVIEW
    for capability in ("household_presence_camera_policy_chain", "household_presence_camera_future_live_deferral_registry", "household_presence_camera_dry_run_continuation_gate"):
        assert RECORDS[capability].status == "implemented"
        assert any("live" in surface for surface in RECORDS[capability].deferred_surfaces)


def test_memory_distillation_context_reflection_is_source_backed() -> None:
    record = RECORDS["selective_memory_distillation_contract"]
    assert record.status == "implemented" and record.authority_level == "metadata_verification_only"
    assert "retain, distill, capsule" in OVERVIEW and "tomb intent is not deletion" in OVERVIEW.lower()
    assert "not a formal Truth Maintenance System" in prose(OVERVIEW)


def test_introspection_self_state_is_evidence_bound() -> None:
    assert "Evidence-bound introspection and self-state" in OVERVIEW
    assert "not perfect self-knowledge or philosophical omniscience" in OVERVIEW


def test_host_interaction_is_source_backed_and_bounded() -> None:
    for capability in ("gui_host_interaction", "browser_host_interaction"):
        assert RECORDS[capability].status == "implemented"
    assert "not amount to universal computer control" in OVERVIEW


def test_maintenance_recursion_through_resident_adoption_is_current() -> None:
    record = RECORDS["maintenance_resident_runtime_adoption"]
    assert record.status == "implemented" and record.authority_level == "bounded-orchestrator"
    assert "CURRENT / IMPLEMENTED BUT BOUNDED" in OVERVIEW
    assert "replace the resident POSIX sentientosd process image" in OVERVIEW


def test_parent_supervision_is_scaffolded_eligibility_only() -> None:
    record = RECORDS["maintenance_resident_parent_supervision"]
    assert (record.status, record.authority_level) == ("scaffolded", "eligibility_only")
    assert "SCAFFOLDED / ELIGIBILITY-ONLY" in OVERVIEW


def test_parent_runtime_and_process_death_recovery_are_unimplemented() -> None:
    record = RECORDS["maintenance_resident_parent_supervision"]
    assert "stable parent runtime implementation" in record.deferred_surfaces
    assert "process-death recovery" in record.deferred_surfaces
    assert "No stable parent runtime is implemented" in OVERVIEW
    assert "No child watcher/restart loop" in OVERVIEW


def test_generic_service_restart_remains_blocked() -> None:
    record = RECORDS["real_service_restart"]
    assert (record.status, record.authority_level) == ("blocked", "none")
    assert "real_service_restart` remains **BLOCKED / none**" in OVERVIEW


def test_stale_pre_resident_maintenance_statement_is_absent() -> None:
    current = README + OVERVIEW
    assert "runtime restart/adoption remain separate" not in current
    assert "runtime restart/adoption. Local absorption" not in current


def test_navigation_exposes_current_architecture() -> None:
    assert "Current Architecture: docs/architecture/public_technical_overview.md" in NAV
    assert "Relationship to Established Terminology" in NAV


def test_terminology_page_exists_and_is_linked() -> None:
    assert Path("docs/architecture/relationship_to_existing_terminology.md").is_file()
    assert "relationship_to_existing_terminology.md" in README
    assert "relationship_to_existing_terminology.md" in OVERVIEW


def test_aos_scaffold_and_cognitive_architecture_are_qualified() -> None:
    assert "agent-operating environment related to AOS literature" in TERMS
    assert "subsystem-level fit** for scaffold/harness" in TERMS
    assert "does not claim a unified psychological theory" in TERMS


def test_social_signal_and_affective_terms_are_qualified() -> None:
    assert "Social signal processing" in TERMS
    assert "observable signal != inferred psychological state != current" in TERMS
    assert "Theory of Mind: **not currently justified**" in TERMS


def test_belief_revision_and_tms_terms_are_qualified() -> None:
    assert "not a formal TMS or ATMS" in TERMS
    assert "general formal justification/dependency-propagation engine" in TERMS


def test_runtime_assurance_and_reference_monitor_are_qualified() -> None:
    assert "not claimed to be a formal global reference monitor" in prose(TERMS)
    assert "Simplex: **not currently justified**" in prose(TERMS)


def test_software_evolution_and_dsu_are_qualified() -> None:
    assert "classic in-place DSU: **not currently justified**" in TERMS
    assert "governed process-image replacement" in TERMS


def test_wifi_rf_claims_remain_deferred() -> None:
    assert "live Wi-Fi/CSI/RF environmental sensing or imaging" in prose(OVERVIEW)
    assert "remain deferred or blocked" in prose(OVERVIEW)
    assert "Wi-Fi/RF sensing" in OVERVIEW and "RESEARCH / TRAJECTORY" in OVERVIEW


def test_consciousness_and_sentience_remain_nonclaims() -> None:
    assert "not evidence of consciousness" in prose(OVERVIEW)
    assert "demonstrated sentience" in OVERVIEW
    assert "not current capability" in TERMS


def test_capability_status_and_prose_drift_contract() -> None:
    assert "repository absorption != runtime adoption" in OVERVIEW
    assert "model output does not grant" in OVERVIEW.lower()
    assert "unrestricted recursive self-improvement" in prose(OVERVIEW)
    assert "global event sourcing" in TERMS
    assert "classic DSU equivalence" in TERMS
