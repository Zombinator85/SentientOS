from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OVERVIEW = "docs/architecture/public_technical_overview.md"
READINESS_INDEX = "docs/architecture/reviewer_release_readiness_index.md"
TRAJECTORY_DOC = "docs/architecture/sentientos_trajectory_and_missing_organs.md"


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
