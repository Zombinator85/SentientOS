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

HOST_EMBODIMENT_PHASE4 = "docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md"


def test_navigation_links_to_host_embodiment_phase4_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    phase1 = _read(HOST_EMBODIMENT_PHASE1)
    phase2 = _read(HOST_EMBODIMENT_PHASE2)
    phase3 = _read(HOST_EMBODIMENT_PHASE3)
    trajectory = _read(TRAJECTORY_DOC)
    assert HOST_EMBODIMENT_PHASE4 in overview
    assert HOST_EMBODIMENT_PHASE4 in index
    assert HOST_EMBODIMENT_PHASE4 in phase1
    assert HOST_EMBODIMENT_PHASE4 in phase2
    assert HOST_EMBODIMENT_PHASE4 in phase3
    assert HOST_EMBODIMENT_PHASE4 in trajectory


def test_phase4_doc_preserves_privilege_broker_boundaries() -> None:
    phase4 = _read(HOST_EMBODIMENT_PHASE4)
    assert "Eligibility is not authorization" in phase4
    assert "broker review receipt is not fulfillment" in phase4 or "broker receipt is not fulfillment" in phase4
    assert "direct fan/PWM/thermal control remains blocked/deferred" in phase4
    assert "future Actuation Fulfillment Layer" in phase4

HOST_EMBODIMENT_PHASE5 = "docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md"


def test_navigation_links_to_host_embodiment_phase5_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    phase1 = _read(HOST_EMBODIMENT_PHASE1)
    phase2 = _read(HOST_EMBODIMENT_PHASE2)
    phase3 = _read(HOST_EMBODIMENT_PHASE3)
    phase4 = _read(HOST_EMBODIMENT_PHASE4)
    trajectory = _read(TRAJECTORY_DOC)
    assert HOST_EMBODIMENT_PHASE5 in overview
    assert HOST_EMBODIMENT_PHASE5 in index
    assert HOST_EMBODIMENT_PHASE5 in phase1
    assert HOST_EMBODIMENT_PHASE5 in phase2
    assert HOST_EMBODIMENT_PHASE5 in phase3
    assert HOST_EMBODIMENT_PHASE5 in phase4
    assert HOST_EMBODIMENT_PHASE5 in trajectory


def test_phase5_doc_preserves_actuation_fulfillment_scaffold_boundaries() -> None:
    phase5 = _read(HOST_EMBODIMENT_PHASE5)
    assert "Fulfillment rehearsal is not real fulfillment" in phase5
    assert "rehearsal receipt is not an effect receipt" in phase5
    assert "No host mutation occurs" in phase5
    assert "No direct fan/PWM control occurs" in phase5
    assert "No thermal actuation occurs" in phase5
    assert "No power profile mutation occurs" in phase5
    assert "No service restart occurs" in phase5
    assert "No cleanup/deletion occurs" in phase5
    assert "control-plane admission" in phase5
    assert "operator/policy approval" in phase5
    assert "effect receipt" in phase5
    assert "postcondition check" in phase5

HOST_EMBODIMENT_EXECUTION_PROOF_WING = "docs/architecture/host_embodiment_execution_proof_wing.md"


def test_navigation_links_to_host_embodiment_execution_proof_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    phase1 = _read(HOST_EMBODIMENT_PHASE1)
    phase2 = _read(HOST_EMBODIMENT_PHASE2)
    phase3 = _read(HOST_EMBODIMENT_PHASE3)
    phase4 = _read(HOST_EMBODIMENT_PHASE4)
    phase5 = _read(HOST_EMBODIMENT_PHASE5)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, phase1, phase2, phase3, phase4, phase5, trajectory]:
        assert HOST_EMBODIMENT_EXECUTION_PROOF_WING in text


def test_execution_proof_wing_doc_preserves_readiness_boundaries() -> None:
    doc = _read(HOST_EMBODIMENT_EXECUTION_PROOF_WING)
    assert "Execution Readiness Manifest is not authorization" in doc
    assert "future effect receipt schema is not proof that an effect occurred" in doc
    assert "does not restart services" in doc
    assert "does not kill processes" in doc
    assert "Real actuation remains deferred" in doc
    for term in ["Effect Receipt", "Postcondition Check", "Rollback Plan", "RollbackReceipt", "Runtime Supervisor", "Execution Readiness Manifest"]:
        assert term in doc

HOST_EMBODIMENT_AUTHORIZATION_REVIEW_WING = "docs/architecture/host_embodiment_authorization_review_wing.md"


def test_navigation_links_to_host_embodiment_authorization_review_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    phase4 = _read(HOST_EMBODIMENT_PHASE4)
    phase5 = _read(HOST_EMBODIMENT_PHASE5)
    execution = _read(HOST_EMBODIMENT_EXECUTION_PROOF_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, phase4, phase5, execution, trajectory]:
        assert HOST_EMBODIMENT_AUTHORIZATION_REVIEW_WING in text


def test_authorization_review_wing_doc_preserves_review_only_boundaries() -> None:
    doc = _read(HOST_EMBODIMENT_AUTHORIZATION_REVIEW_WING)
    assert "authorization review is not authorization grant" in doc
    assert "Future Authorization Grant schema is not a real grant" in doc or "future authorization grant schema is not a real grant" in doc
    assert "Real fulfillment remains deferred" in doc
    assert "Real actuation remains deferred" in doc
    assert "No host mutation" in doc or "not host mutation" in doc
    for term in ["AuthorizationReviewPacket", "AuthorizationReviewDecision", "AuthorizationReviewReceipt", "FutureAuthorizationGrantSchema"]:
        assert term in doc

HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING = "docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md"


def test_navigation_links_to_controlled_authorization_trace_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    auth = _read(HOST_EMBODIMENT_AUTHORIZATION_REVIEW_WING)
    proof = _read(HOST_EMBODIMENT_EXECUTION_PROOF_WING)
    phase5 = _read(HOST_EMBODIMENT_PHASE5)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, auth, proof, phase5, trajectory]:
        assert HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING in text


def test_controlled_authorization_trace_doc_preserves_non_live_boundaries() -> None:
    doc = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    assert "controlled authorization contract is not a live grant" in doc
    assert "grant record is schema-only/future-use-only" in doc
    assert "Demo trace is reviewer proof only" in doc or "demo trace is reviewer proof only" in doc
    assert "Real fulfillment remains deferred" in doc
    assert "Real actuation remains deferred" in doc

HOST_EMBODIMENT_REVIEWER_DEMO_TRACE = "docs/architecture/host_embodiment_reviewer_demo_trace.md"


def test_navigation_links_to_host_embodiment_reviewer_demo_trace_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    auth = _read(HOST_EMBODIMENT_AUTHORIZATION_REVIEW_WING)
    proof = _read(HOST_EMBODIMENT_EXECUTION_PROOF_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, controlled, auth, proof, trajectory]:
        assert HOST_EMBODIMENT_REVIEWER_DEMO_TRACE in text


def test_reviewer_demo_trace_doc_preserves_demo_boundaries_and_commands() -> None:
    doc = _read(HOST_EMBODIMENT_REVIEWER_DEMO_TRACE)
    for command in [
        "python scripts/build_host_embodiment_trace.py --format json",
        "python scripts/build_host_embodiment_trace.py --format markdown",
        "python scripts/build_host_embodiment_trace.py --validate-only",
    ]:
        assert command in doc
    assert "demo trace is reviewer proof only" in doc.lower()
    assert "no host mutation" in doc.lower()
    assert "PWM presence is not control authority" in doc
    assert "controlled authorization contract is not a live grant" in doc
    assert "schema-only/future-use-only" in doc

REVIEWER_FIRST_RUN_PROOF_BUNDLE = "docs/architecture/reviewer_first_run_proof_bundle.md"


def test_navigation_links_to_reviewer_first_run_proof_bundle_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    trajectory = _read(TRAJECTORY_DOC)
    reviewer_demo = _read(HOST_EMBODIMENT_REVIEWER_DEMO_TRACE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    for text in [overview, index, trajectory, reviewer_demo, controlled]:
        assert REVIEWER_FIRST_RUN_PROOF_BUNDLE in text


def test_reviewer_first_run_proof_bundle_doc_preserves_boundary_and_file_list() -> None:
    doc = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    assert "python scripts/build_reviewer_proof_bundle.py --output-dir /tmp/sentientos-reviewer-proof" in doc
    assert "fake/sample thermal+PWM telemetry" in doc
    assert "does not collect live host data by default" in doc
    assert "does not mutate host state" in doc
    for filename in [
        "trace.json",
        "trace.md",
        "trace.summary.txt",
        "capability_registry_summary.json",
        "deferred_actions.json",
        "safety_gates.json",
        "proof_commands.json",
        "README.md",
        "bundle_manifest.json",
    ]:
        assert filename in doc

HOST_ACTUATION_SAFETY_GATE_WING = "docs/architecture/host_actuation_safety_gate_wing.md"


def test_navigation_links_to_host_actuation_safety_gate_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    bundle = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    for text in [overview, index, bundle, controlled]:
        assert HOST_ACTUATION_SAFETY_GATE_WING in text


def test_host_actuation_safety_gate_doc_preserves_safety_only_boundaries() -> None:
    doc = _read(HOST_ACTUATION_SAFETY_GATE_WING)
    assert "Safety gates are not authorization" in doc
    assert "Hardware allowlist does not grant control" in doc
    assert "OS backend declaration does not load/invoke backend" in doc
    assert "Panic stop contract does not execute panic stop" in doc
    assert "Real actuation remains deferred" in doc
    assert "observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → authorize" in doc

HOST_LIVE_GRANT_READINESS_WING = "docs/architecture/host_live_grant_readiness_wing.md"


def test_navigation_links_to_host_live_grant_readiness_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    safety = _read(HOST_ACTUATION_SAFETY_GATE_WING)
    bundle = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, safety, bundle, controlled, trajectory]:
        assert HOST_LIVE_GRANT_READINESS_WING in text


def test_host_live_grant_readiness_doc_preserves_preflight_only_boundaries() -> None:
    doc = _read(HOST_LIVE_GRANT_READINESS_WING)
    assert "Live-grant readiness is not a live grant" in doc
    assert "operator/policy approval packet is not approval" in doc
    assert "grant issue preflight receipt does not issue a grant" in doc
    assert "Real actuation remains deferred" in doc
    assert "observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → authorize" in doc

HOST_LOCAL_AUTHORIZATION_GRANT_WING = "docs/architecture/host_local_authorization_grant_wing.md"


def test_navigation_links_to_host_local_authorization_grant_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    safety = _read(HOST_ACTUATION_SAFETY_GATE_WING)
    live = _read(HOST_LIVE_GRANT_READINESS_WING)
    bundle = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, safety, live, bundle, controlled, trajectory]:
        assert HOST_LOCAL_AUTHORIZATION_GRANT_WING in text


def test_host_local_authorization_grant_doc_preserves_record_only_boundaries() -> None:
    doc = _read(HOST_LOCAL_AUTHORIZATION_GRANT_WING)
    assert "A local authorization grant is authority metadata, not fulfillment" in doc
    assert "A local authorization grant does not execute" in doc
    assert "A local authorization grant does not mutate host state" in doc
    assert "Grant verification is not fulfillment authorization" in doc
    assert "revocation receipt records revocation metadata and does not execute host action" in doc
    assert "Expiry evaluation is metadata-only" in doc
    assert "Real actuation remains deferred" in doc
    assert "observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → local authorization grant → fulfill" in doc

HOST_FULFILLMENT_AUTHORIZATION_CONSUMPTION_WING = "docs/architecture/host_fulfillment_authorization_consumption_wing.md"


def test_navigation_links_to_host_fulfillment_authorization_consumption_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    local = _read(HOST_LOCAL_AUTHORIZATION_GRANT_WING)
    live = _read(HOST_LIVE_GRANT_READINESS_WING)
    bundle = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, local, live, bundle, controlled, trajectory]:
        assert HOST_FULFILLMENT_AUTHORIZATION_CONSUMPTION_WING in text


def test_host_fulfillment_authorization_consumption_doc_preserves_pre_fulfillment_boundaries() -> None:
    doc = _read(HOST_FULFILLMENT_AUTHORIZATION_CONSUMPTION_WING)
    assert "Fulfillment authorization consumption is not fulfillment" in doc
    assert "Scope match is not execution" in doc
    assert "A consumption receipt does not execute" in doc
    assert "A denial receipt does not execute" in doc
    assert "Real actuation remains deferred" in doc
    assert "observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → local authorization grant → fulfillment authorization consumption → fulfill" in doc


def test_reviewer_first_run_proof_bundle_doc_lists_fulfillment_authorization_artifact() -> None:
    doc = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    assert "fulfillment_authorization.json" in doc
    assert "consuming authorization is not fulfillment" in doc

HOST_FULFILLMENT_EXECUTOR_CONTRACT_WING = "docs/architecture/host_fulfillment_executor_contract_wing.md"


def test_navigation_links_to_host_fulfillment_executor_contract_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    consumption = _read(HOST_FULFILLMENT_AUTHORIZATION_CONSUMPTION_WING)
    local = _read(HOST_LOCAL_AUTHORIZATION_GRANT_WING)
    bundle = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, consumption, local, bundle, controlled, trajectory]:
        assert HOST_FULFILLMENT_EXECUTOR_CONTRACT_WING in text


def test_host_fulfillment_executor_contract_doc_preserves_contract_only_boundaries() -> None:
    doc = _read(HOST_FULFILLMENT_EXECUTOR_CONTRACT_WING)
    assert "executor contract is not an executor" in doc.lower()
    assert "backend declaration does not load or invoke backend" in doc
    assert "dry-run plan is not dry-run execution" in doc
    assert "admission packet is not control-plane admission" in doc
    assert "Real actuation remains deferred" in doc
    assert "executor_implemented=false" in doc
    assert "backend_loaded=false" in doc
    assert "dry_run_executed=false" in doc
    assert "control_plane_admission_granted=false" in doc
    assert "fulfillment_granted=false" in doc
    assert "effect_performed=false" in doc
    assert "host_mutation_performed=false" in doc


def test_reviewer_first_run_proof_bundle_doc_lists_executor_contract_artifact() -> None:
    doc = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    assert "executor_contract.json" in doc
    assert "executor contract is not an executor" in doc.lower()

HOST_DRY_RUN_EXECUTION_HARNESS_WING = "docs/architecture/host_dry_run_execution_harness_wing.md"


def test_navigation_links_to_host_dry_run_execution_harness_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    executor = _read(HOST_FULFILLMENT_EXECUTOR_CONTRACT_WING)
    bundle = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, executor, bundle, controlled, trajectory]:
        assert HOST_DRY_RUN_EXECUTION_HARNESS_WING in text


def test_host_dry_run_execution_harness_doc_preserves_simulation_only_boundaries() -> None:
    doc = _read(HOST_DRY_RUN_EXECUTION_HARNESS_WING)
    assert "runs only inert simulated backends" in doc or "only inert, deterministic, in-process simulated backend" in doc
    assert "Dry-run execution is not real fulfillment" in doc
    assert "A dry-run result is not an effect receipt" in doc
    assert "A dry-run receipt is not proof of host mutation" in doc
    assert "Real actuation remains deferred" in doc
    assert "subprocess execution" in doc
    assert "network egress" in doc

HOST_DRY_RUN_AUDIT_CLOSURE_WING = "docs/architecture/host_dry_run_audit_closure_wing.md"


def test_navigation_links_to_host_dry_run_audit_closure_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    dry_run = _read(HOST_DRY_RUN_EXECUTION_HARNESS_WING)
    bundle = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, dry_run, bundle, controlled, trajectory]:
        assert HOST_DRY_RUN_AUDIT_CLOSURE_WING in text


def test_host_dry_run_audit_closure_doc_preserves_dry_run_only_boundaries() -> None:
    doc = _read(HOST_DRY_RUN_AUDIT_CLOSURE_WING)
    assert "Dry-run effect verification is not a real effect receipt" in doc
    assert "Dry-run postcondition verification is not a real host postcondition check" in doc
    assert "Dry-run rollback rehearsal is not real rollback" in doc
    assert "Dry-run audit closure is not a production audit receipt" in doc
    assert "Real actuation remains deferred" in doc
    assert "No subprocess" in doc or "no subprocess" in doc

HOST_REAL_EFFECT_CAPABILITY_ADMISSION_WING = "docs/architecture/host_real_effect_capability_admission_wing.md"


def test_navigation_links_to_host_real_effect_capability_admission_wing_doc() -> None:
    overview = _read(PUBLIC_OVERVIEW)
    index = _read(READINESS_INDEX)
    dry_run = _read(HOST_DRY_RUN_EXECUTION_HARNESS_WING)
    closure = _read(HOST_DRY_RUN_AUDIT_CLOSURE_WING)
    bundle = _read(REVIEWER_FIRST_RUN_PROOF_BUNDLE)
    controlled = _read(HOST_EMBODIMENT_CONTROLLED_AUTHORIZATION_TRACE_WING)
    trajectory = _read(TRAJECTORY_DOC)
    for text in [overview, index, dry_run, closure, bundle, controlled, trajectory]:
        assert HOST_REAL_EFFECT_CAPABILITY_ADMISSION_WING in text


def test_host_real_effect_capability_admission_doc_preserves_planning_only_boundaries() -> None:
    doc = _read(HOST_REAL_EFFECT_CAPABILITY_ADMISSION_WING)
    assert "Dry-run audit closure verifies simulated evidence only" in doc
    assert "Real effect capability admission is not implementation" in doc
    assert "admission decision does not authorize implementation or execution" in doc
    assert "implementation plan scaffold does not start implementation" in doc
    assert "Cooling/hardware control remains blocked by default" in doc
    assert "Real actuation remains deferred" in doc
    assert "Real fulfillment remains deferred" in doc
    assert "Real effect receipts remain deferred" in doc
    assert "Real postcondition checks remain deferred" in doc
    assert "Real rollback remains deferred" in doc
    assert "Production audit remains deferred" in doc


def test_local_diagnostic_effect_pilot_doc_is_linked_and_preserves_boundaries() -> None:
    doc = Path("docs/architecture/host_local_diagnostic_effect_pilot_wing.md").read_text(encoding="utf-8")
    public = Path("docs/architecture/public_technical_overview.md").read_text(encoding="utf-8")
    index = Path("docs/architecture/reviewer_release_readiness_index.md").read_text(encoding="utf-8")
    assert "host_local_diagnostic_effect_pilot_wing.md" in public
    assert "host_local_diagnostic_effect_pilot_wing.md" in index
    assert "first intentionally real effect pilot" in doc
    assert "one deterministic metadata/diagnostic artifact" in doc
    assert "does not run this effect by default" in doc
    assert "fan/PWM control" in doc and "thermal actuation" in doc and "service restart" in doc
    assert "network egress" in doc and "provider invocation" in doc and "prompt assembly" in doc
    assert "subprocess execution" in doc and "shell execution" in doc
    assert "python scripts/run_local_diagnostic_effect.py --output-dir /tmp/sentientos-local-diagnostic-effect --summary" in doc
