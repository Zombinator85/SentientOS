from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "architecture/local_cognitive_compute_substrate_architecture.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_has_required_architecture_sections() -> None:
    required = {
        "current_stack", "delegated_components", "terminology",
        "trust_and_authority_boundaries", "identity_distinctions",
        "correctness_equivalence_contract", "performance_evidence_contract",
        "candidate_lifecycle", "portability_posture",
        "capability_preservation_posture", "considered_ownership_models",
        "selected_architecture", "explicit_non_goals", "threat_and_failure_model",
        "next_implementation_slice",
    }
    assert CONTRACT["schema"] == "sentientos.local_cognitive_compute_substrate_architecture:v1"
    assert CONTRACT["status"] == "architecture_only"
    assert required <= CONTRACT.keys()


def test_stack_separates_model_runtime_backend_kernel_and_hardware() -> None:
    terms = CONTRACT["terminology"]
    assert {
        "model_identity", "model_artifact", "quantization", "inference_runtime",
        "runtime_build", "accelerator_backend", "execution_primitive",
        "kernel_artifact", "hardware", "driver_runtime_stack", "compute_profile",
        "performance_evidence",
    } <= terms.keys()
    invariants = CONTRACT["identity_distinctions"]["invariants"]
    assert "model_identity != inference_runtime" in invariants
    assert "accelerator_backend != kernel_artifact" in invariants
    assert "kernel_artifact != hardware" in invariants
    assert len(CONTRACT["current_stack"]) == 8
    assert [item["order"] for item in CONTRACT["current_stack"]] == list(range(1, 9))


def test_current_reality_and_delegation_are_truthful() -> None:
    reality = CONTRACT["verified_current_reality"]
    assert reality["routes"] == ["cpu", "cuda", "rocm", "metal"]
    assert reality["llama_cpp_worker_parameters"] == ["n_gpu_layers", "n_ctx"]
    assert reality["custom_kernel_posture"] == "none owned as a general-purpose production substrate"
    assert "separate" in reality["availability_distinction"]
    inventory = CONTRACT["vendored_llama_cpp_inventory"]
    assert inventory["file_count"] == 7
    assert "CUDA kernels" in inventory["absent"]
    assert "not a complete owned llama.cpp accelerator stack" in inventory["conclusion"]


def test_governed_extension_is_the_only_selected_ownership_model() -> None:
    choices = CONTRACT["considered_ownership_models"]
    assert {item["id"] for item in choices} == {
        "pure_delegation", "governed_extension", "independent_runtime"
    }
    assert [item["id"] for item in choices if item["decision"] == "select"] == [
        "governed_extension"
    ]
    assert CONTRACT["selected_architecture"]["posture"] == "governed_extension"
    assert "llama.cpp" in CONTRACT["selected_architecture"]["delegation_default"]


def test_correctness_performance_and_adoption_do_not_collapse() -> None:
    correctness = CONTRACT["correctness_equivalence_contract"]
    assert "approximately looks right is forbidden" in correctness["admission_rule"]
    assert any("logit" in item for item in correctness["required_evidence"])
    performance = CONTRACT["performance_evidence_contract"]
    assert "time_to_first_token" in performance["required_measurements"]
    assert "peak_vram" in performance["required_measurements"]
    assert "correctness_equivalence_result" in performance["required_measurements"]
    assert "cannot authorize adoption" in performance["authority"]
    assert CONTRACT["candidate_lifecycle"] == [
        "candidate_optimization", "build_or_compile", "functional_verification",
        "numerical_or_equivalence_verification", "performance_measurement",
        "comparison", "review_and_policy", "adoption", "post_adoption_measurement",
    ]


def test_portability_security_and_resource_boundaries_fail_closed() -> None:
    assert CONTRACT["portability_posture"]["families"] == ["cpu", "cuda", "rocm", "metal"]
    boundaries = CONTRACT["trust_and_authority_boundaries"]
    assert "faster_kernel_grants_no_authority" in boundaries
    assert "generated_optimization_grants_no_adoption" in boundaries
    resource = CONTRACT["resource_principal_connection"]
    assert "does not create ResourceAllocation" in resource["boundary"]
    assert CONTRACT["orthogonal_roadmap"]["resource_principal_next_runtime_slice"] == (
        "production_purpose_scoped_root_issuer_provenance_signer"
    )
    assert CONTRACT["orthogonal_roadmap"]["status"] == (
        "deferred_not_cancelled_and_not_implemented_by_this_task"
    )


def test_training_named_surfaces_do_not_claim_weight_training() -> None:
    classifications = CONTRACT["training_surface_classification"]
    assert {item["path"] for item in classifications} == {
        "sentientos/codex/self_training_daemon.py", "codex_retraining_planner.py",
        "sentientos/codex/retraining_prep.py", "sentientos/forge_merge_train.py",
    }
    assert all(item["weight_training"] is False for item in classifications)
    assert {item["classification"] for item in classifications} == {
        "software_improvement_orchestration", "dataset_and_plan_preparation",
        "software_merge_train",
    }
    assert CONTRACT["training_conclusion"] == (
        "No inspected surface provides a production model-weight training path."
    )


def test_contract_selects_exactly_one_non_kernel_next_slice() -> None:
    next_slice = CONTRACT["next_implementation_slice"]
    assert next_slice["count"] == 1
    assert next_slice["id"] == "exact_runtime_backend_build_identity_and_benchmark_manifest"
    assert "implement_a_kernel" in next_slice["must_not"]
    assert "metadata-only manifest" in next_slice["scope"]


def test_all_evidence_sources_and_companion_document_exist() -> None:
    assert all((ROOT / path).is_file() for path in CONTRACT["evidence_sources"])
    companion = ROOT / "docs/architecture/local_cognitive_compute_substrate_architecture.md"
    text = companion.read_text(encoding="utf-8")
    assert "Local Cognitive Compute Substrate" in text
    assert "exact_runtime_backend_build_identity_and_benchmark_manifest" in text
    assert "production_purpose_scoped_root_issuer_provenance_signer" in text
