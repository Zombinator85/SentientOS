from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OVERVIEW = "docs/architecture/public_technical_overview.md"
READINESS_INDEX = "docs/architecture/reviewer_release_readiness_index.md"
TRAJECTORY_DOC = "docs/architecture/sentientos_trajectory_and_missing_organs.md"
HOST_EMBODIMENT_PHASE1 = "docs/architecture/host_embodiment_substrate_phase1.md"
HOST_EMBODIMENT_PHASE2 = "docs/architecture/host_embodiment_substrate_phase2_read_only_discovery.md"


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_readme_points_reviewers_to_public_technical_overview() -> None:
    readme = _read("README.md")
    assert PUBLIC_OVERVIEW in readme


def test_public_overview_points_to_release_readiness_index() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    assert READINESS_INDEX in overview


def test_release_readiness_index_keeps_key_proof_commands_current() -> None:
    index = _read(READINESS_INDEX)
    expected_commands = [
        "python -m scripts.run_tests -q tests/test_control_plane_kernel.py tests/test_sentientosd_runtime_closure.py",
        "python -m scripts.run_tests -q tests/test_trust_ledger.py sentientos/tests/test_trust_ledger_recovery.py",
        "python -m scripts.run_tests -q tests/test_chat_service_lazy_loading.py tests/test_local_model.py tests/integration/test_chat_mistral_runtime.py",
        "python -m scripts.run_tests -q tests/test_federated_improvement_candidate.py tests/test_federated_improvement_intake_receipt.py tests/test_federated_improvement_custody_runway.py tests/test_federated_improvement_local_variant_artifact.py tests/test_federated_improvement_lineage_comparison_receipt.py tests/test_federated_improvement_dissemination_receipt.py",
        "python scripts/verify_context_hygiene_prompt_boundaries.py",
        "python scripts/verify_audits.py --strict",
        "python scripts/audit_immutability_verifier.py --manifest vow/immutable_manifest.json",
        "python scripts/build_docs.py --check-deps",
        "python scripts/build_docs.py",
    ]
    for command in expected_commands:
        assert command in index


def test_navigation_links_to_trajectory_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    assert TRAJECTORY_DOC in overview
    assert TRAJECTORY_DOC in index


def test_navigation_links_to_host_embodiment_phase1_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    trajectory = _read(TRAJECTORY_DOC)
    assert HOST_EMBODIMENT_PHASE1 in overview
    assert HOST_EMBODIMENT_PHASE1 in index
    assert HOST_EMBODIMENT_PHASE1 in trajectory


def test_trajectory_doc_clarifies_deferred_fan_pwm_and_missing_organs() -> None:
    trajectory = _read(TRAJECTORY_DOC)
    assert "Direct fan/PWM control is deferred" in trajectory
    expected_organs = [
        "Host Resource Governor",
        "Privilege Broker",
        "Actuation Fulfillment Layer",
        "Hardware/Sensor Inventory Manifest",
        "Runtime Supervisor",
        "Capability Registry",
        "Local Model Authority Map",
        "World-State Board",
        "Federation Transport Envelope",
        "External Reviewer Demo Script",
    ]
    for organ in expected_organs:
        assert organ in trajectory


def test_host_embodiment_docs_preserve_phase1_boundaries() -> None:
    combined = "\n".join(
        [
            _read(HOST_EMBODIMENT_PHASE1),
            _read(PUBLIC_OVERVIEW),
            _read(READINESS_INDEX),
            _read(TRAJECTORY_DOC),
        ]
    )
    assert "direct fan/PWM control remains deferred" in combined
    for term in [
        "Capability Registry",
        "Hardware/Sensor Inventory Manifest",
        "Host Resource Governor",
        "Privilege Broker",
        "Actuation Fulfillment Layer",
    ]:
        assert term in combined



def test_navigation_links_to_host_embodiment_phase2_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    phase1 = _read(HOST_EMBODIMENT_PHASE1)
    trajectory = _read(TRAJECTORY_DOC)
    assert HOST_EMBODIMENT_PHASE2 in overview
    assert HOST_EMBODIMENT_PHASE2 in index
    assert HOST_EMBODIMENT_PHASE2 in phase1
    assert HOST_EMBODIMENT_PHASE2 in trajectory


def test_phase2_doc_preserves_read_only_discovery_boundaries() -> None:
    phase2 = _read(HOST_EMBODIMENT_PHASE2)
    assert "direct fan/PWM writes remain forbidden/deferred" in phase2
    assert "PWM presence is not control authority" in phase2
    assert "Privilege Broker" in phase2
    assert "Actuation Fulfillment Layer" in phase2

HOST_EMBODIMENT_PHASE3 = "docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md"


def test_navigation_links_to_host_embodiment_phase3_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    phase1 = _read(HOST_EMBODIMENT_PHASE1)
    phase2 = _read(HOST_EMBODIMENT_PHASE2)
    trajectory = _read(TRAJECTORY_DOC)
    assert HOST_EMBODIMENT_PHASE3 in overview
    assert HOST_EMBODIMENT_PHASE3 in index
    assert HOST_EMBODIMENT_PHASE3 in phase1
    assert HOST_EMBODIMENT_PHASE3 in phase2
    assert HOST_EMBODIMENT_PHASE3 in trajectory


def test_phase3_doc_preserves_proposal_receipt_boundaries() -> None:
    phase3 = _read(HOST_EMBODIMENT_PHASE3)
    assert "Proposal receipts are not effects" in phase3
    assert "policy decision is not authorization" in phase3
    assert "PWM presence is not control authority" in phase3
    assert "Privilege Broker" in phase3
    assert "Actuation Fulfillment Layer" in phase3
