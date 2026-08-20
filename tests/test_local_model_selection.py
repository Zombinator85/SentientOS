from __future__ import annotations

import copy

import pytest

from types import SimpleNamespace

from sentientos.host_collectors import (
    HostCollectorResult,
    collect_accelerator_observation,
    collect_cpu_feature_observation,
    collect_disk_observation,
    collect_memory_observation,
)
from sentientos.host_inventory import build_host_inventory_from_collector_results

from sentientos.host_inventory import build_host_inventory_manifest
from sentientos.local_model_selection import GIB, LocalInferenceHardwareProfile, hardware_profile_from_inventory, plan_local_model_selection

pytestmark = pytest.mark.no_legacy_skip


def profile(**changes: object) -> LocalInferenceHardwareProfile:
    values = dict(source_inventory_id="test", source_inventory_digest="0" * 64, os_family="linux", architecture="amd64",
                  total_ram_bytes=16 * GIB, avx=True, avx2=True, avx512=False)
    values.update(changes)
    return LocalInferenceHardwareProfile(**values)


def candidate(model_id: str = "cpu", priority: int = 1, **requirements: object) -> dict:
    req = dict(architecture="x86_64", ram_gb_min=8, avx=False, avx2=True, avx512=False, gpu=False, quantization="q4")
    req.update(requirements)
    return {"id": model_id, "priority": priority, "license": "apache-2.0", "requirements": req,
            "artifact": {"sha256": (model_id[0] * 64), "size_bytes": 123, "escrow_path": f"escrow/{model_id}.gguf", "urls": [f"https://models.sentientos.org/{model_id}.gguf"]}}


def manifest(*models: dict) -> dict:
    return {"manifest_version": "v1", "models": list(models)}


def v2_candidate(model_id: str = "v2", priority: int = 1, *, routes: list[dict] | None = None) -> dict:
    item = candidate(model_id, priority)
    item["requirements"].pop("gpu")
    item["execution_routes"] = routes or [{"route_id": "llama-cpp-cpu", "engine": "llama_cpp", "backend_family": "cpu", "route_priority": 20}]
    return item


def v2_manifest(*models: dict) -> dict:
    return {"schema_version": "sentientos.model_manifest:v2", "manifest_version": "routes-1", "models": list(models)}


def test_deterministic_host_profile_maps_only_explicit_inventory_facts() -> None:
    inventory = build_host_inventory_manifest(manifest_id="i", node_id="n", architecture="aarch64", os_family="linux",
        cpu_summary={"model": "AVX512 words are not evidence", "avx2": True}, ram_summary={"total_bytes": 8 * GIB},
        gpu_summary={"vendor": "NVIDIA"}, observed_at="fixed")
    first = hardware_profile_from_inventory(inventory)
    second = hardware_profile_from_inventory(inventory)
    assert first.digest == second.digest
    assert (first.architecture, first.avx, first.avx2, first.avx512) == ("aarch64", "unknown", True, "unknown")
    assert first.backend_family is None and first.vram_bytes is None


def test_exact_ram_and_collector_free_storage_handoff() -> None:
    ram, free = 17_179_869_184, 9_876_543_210
    inventory = build_host_inventory_from_collector_results((
        collect_memory_observation(memory_provider=lambda: {"total_bytes": ram}, observed_at="fixed"),
        collect_disk_observation(disk_provider=lambda path: SimpleNamespace(total=20_000_000_000, used=10_123_456_790, free=free), observed_at="fixed"),
    ), manifest_id="facts", node_id="node")
    observed = hardware_profile_from_inventory(inventory)
    assert observed.total_ram_bytes == ram
    assert observed.available_storage_bytes == free


def _observed_inventory(*, feature_text: str | None, accelerator: HostCollectorResult | None = None):
    platform_result = HostCollectorResult(
        collector_id="platform", status="available", observed_at="fixed", source="injected:platform",
        values={"os_family": "linux", "os_release": "test", "architecture": "x86_64", "cpu_count": 8},
    )
    reader = ((lambda path: feature_text) if feature_text is not None else
              (lambda path: (_ for _ in ()).throw(OSError())))
    results = [platform_result,
               collect_memory_observation(memory_provider=lambda: {"total_bytes": 16 * GIB}, observed_at="fixed"),
               collect_disk_observation(disk_provider=lambda path: SimpleNamespace(total=40 * GIB, used=8 * GIB, free=32 * GIB), observed_at="fixed"),
               collect_cpu_feature_observation(system="Linux", architecture="x86_64", text_reader=reader, observed_at="fixed")]
    if accelerator is not None:
        results.append(accelerator)
    return build_host_inventory_from_collector_results(results, manifest_id="observed", node_id="node")


def test_read_only_observation_to_selection_end_to_end_succeeds() -> None:
    inventory = _observed_inventory(feature_text="flags: sse avx avx2\n")
    observed = hardware_profile_from_inventory(inventory)
    plan = plan_local_model_selection(observed, manifest(candidate()))
    assert observed.avx is True and observed.avx2 is True
    assert plan["status"] == "selected" and plan["selected"]["model_id"] == "cpu"


def test_unknown_observed_cpu_feature_fails_closed_end_to_end() -> None:
    observed = hardware_profile_from_inventory(_observed_inventory(feature_text=None))
    plan = plan_local_model_selection(observed, manifest(candidate()))
    assert observed.avx2 == "unknown" and "avx2_unknown" in observed.missing_fact_codes
    assert plan["status"] == "blocked_missing_hardware_facts"


def test_accelerator_observation_does_not_imply_backend_or_change_cpu_eligibility() -> None:
    files = {"/drm/card0/device/vendor": "0x10de", "/drm/card0/device/device": "0xbeef"}
    accelerator = collect_accelerator_observation(
        system="Linux", drm_path="/drm", directory_lister=lambda path: ("card0",), text_reader=lambda path: files.get(path), observed_at="fixed",
    )
    observed = hardware_profile_from_inventory(_observed_inventory(feature_text="flags: avx avx2\n", accelerator=accelerator))
    assert observed.accelerator_observed is True and observed.accelerator_vendor == "nvidia"
    assert observed.vram_bytes is None and observed.backend_family is None
    assert plan_local_model_selection(observed, manifest(candidate()))["status"] == "selected"
    gpu_plan = plan_local_model_selection(observed, manifest(candidate("gpu", gpu=True)))
    assert gpu_plan["reason_codes"] == ("manifest_accelerator_backend_unspecified",)


def test_successful_selection_alias_ram_and_cpu_feature_semantics() -> None:
    plan = plan_local_model_selection(profile(), manifest(candidate()))
    assert plan["status"] == "selected"
    assert plan["selected"]["model_id"] == "cpu"


def test_incompatible_architecture_and_ram_are_excluded() -> None:
    plan = plan_local_model_selection(profile(total_ram_bytes=4 * GIB), manifest(candidate(architecture="arm64")))
    assert plan["status"] == "blocked_no_eligible_model"
    assert set(plan["candidate_summaries"][0]["reason_codes"]) == {"architecture_mismatch", "insufficient_ram"}


def test_unknown_ram_and_features_fail_closed() -> None:
    plan = plan_local_model_selection(profile(total_ram_bytes=None, avx2="unknown"), manifest(candidate()))
    assert plan["status"] == "blocked_missing_hardware_facts"
    assert set(plan["reason_codes"]) == {"avx2_unknown", "ram_unknown"}


def test_avx2_and_avx512_missing_and_present_cases() -> None:
    required = candidate(avx512=True)
    assert plan_local_model_selection(profile(avx512=True), manifest(required))["status"] == "selected"
    reasons = plan_local_model_selection(profile(avx2=False), manifest(candidate()))["reason_codes"]
    assert reasons == ("avx2_missing",)
    reasons = plan_local_model_selection(profile(avx512=False), manifest(required))["reason_codes"]
    assert reasons == ("avx512_missing",)
    reasons = plan_local_model_selection(profile(avx512="unknown"), manifest(required))["reason_codes"]
    assert reasons == ("avx512_unknown",)


def test_gpu_v1_is_unresolved_but_cpu_candidate_is_eligible() -> None:
    plan = plan_local_model_selection(profile(accelerator_observed=True), manifest(candidate("gpu", gpu=True), candidate("cpu", 2)))
    assert plan["status"] == "selected" and plan["selected"]["model_id"] == "cpu"
    assert plan["candidate_summaries"][0]["reason_codes"] == ("manifest_accelerator_backend_unspecified",)


def test_v2_explicit_cuda_route_selects_without_runtime_inspection() -> None:
    cuda = {"route_id": "cuda", "engine": "llama_cpp", "backend_family": "cuda",
            "accelerator_vendor": "nvidia", "min_vram_bytes": 8 * GIB, "route_priority": 10}
    plan = plan_local_model_selection(profile(accelerator_observed=True, accelerator_vendor="nvidia", vram_bytes=12 * GIB),
                                      v2_manifest(v2_candidate(routes=[cuda])))
    assert plan["status"] == "selected"
    assert plan["selected"]["route_id"] == "cuda"
    assert plan["selected"]["runtime_requirement"] == {"engine": "llama_cpp", "backend_family": "cuda"}
    assert plan["selected"]["runtime_availability_status"] == "not_evaluated"
    assert plan["selected"]["runtime_provisioning_required"] == "unknown"


def test_v2_routes_rank_and_unresolved_accelerator_falls_back_to_cpu() -> None:
    routes = [
        {"route_id": "cuda", "engine": "llama_cpp", "backend_family": "cuda", "accelerator_vendor": "nvidia", "route_priority": 10},
        {"route_id": "cpu", "engine": "llama_cpp", "backend_family": "cpu", "route_priority": 20},
    ]
    unresolved = plan_local_model_selection(profile(), v2_manifest(v2_candidate(routes=routes)))
    assert unresolved["selected"]["route_id"] == "cpu"
    accelerated = plan_local_model_selection(profile(accelerator_observed=True, accelerator_vendor="nvidia"), v2_manifest(v2_candidate(routes=routes)))
    assert accelerated["selected"]["route_id"] == "cuda"


def test_v2_rocm_vendor_and_vram_fail_closed() -> None:
    rocm = {"route_id": "rocm", "engine": "llama_cpp", "backend_family": "rocm", "accelerator_vendor": "amd",
            "min_vram_bytes": 8 * GIB, "route_priority": 1}
    unknown = plan_local_model_selection(profile(accelerator_observed=True, accelerator_vendor="amd"), v2_manifest(v2_candidate(routes=[rocm])))
    assert unknown["reason_codes"] == ("vram_unknown",)
    small = plan_local_model_selection(profile(accelerator_observed=True, accelerator_vendor="amd", vram_bytes=4 * GIB), v2_manifest(v2_candidate(routes=[rocm])))
    assert small["reason_codes"] == ("insufficient_vram",)
    mismatch = plan_local_model_selection(profile(accelerator_observed=True, accelerator_vendor="nvidia", vram_bytes=12 * GIB), v2_manifest(v2_candidate(routes=[rocm])))
    assert mismatch["reason_codes"] == ("accelerator_vendor_mismatch",)


def test_v2_same_artifact_multiple_routes_and_input_order_are_deterministic() -> None:
    routes = [
        {"route_id": "cuda", "engine": "llama_cpp", "backend_family": "cuda", "accelerator_vendor": "nvidia", "route_priority": 1},
        {"route_id": "cpu", "engine": "llama_cpp", "backend_family": "cpu", "route_priority": 2},
    ]
    one, two = v2_candidate("a", routes=routes), v2_candidate("b", routes=routes)
    first = plan_local_model_selection(profile(), v2_manifest(one, two))
    second = plan_local_model_selection(profile(), v2_manifest(two, one))
    assert first == second and len(first["candidate_summaries"]) == 4


def test_priority_falls_through_incompatible_and_unresolved_candidates() -> None:
    plan = plan_local_model_selection(profile(), manifest(candidate("wrong", 1, architecture="arm64"), candidate("gpu", 2, gpu=True), candidate("ok", 3)))
    assert plan["selected"]["model_id"] == "ok"


def test_candidate_order_and_plan_digest_are_deterministic() -> None:
    a, b = candidate("b", 1), candidate("a", 1)
    first = plan_local_model_selection(profile(), manifest(a, b))
    second = plan_local_model_selection(profile(), manifest(b, a))
    assert [item["model_id"] for item in first["eligible_candidates"]] == ["a", "b"]
    assert first == second and first["plan_digest"] == second["plan_digest"]


def test_no_eligible_and_malformed_manifest_block() -> None:
    assert plan_local_model_selection(profile(), manifest(candidate(architecture="arm64")))["status"] == "blocked_no_eligible_model"
    assert plan_local_model_selection(profile(), {"models": []})["status"] == "blocked_manifest_invalid"


def test_planner_is_zero_effect_metadata(monkeypatch) -> None:
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    before = copy.deepcopy(profile().to_dict())
    plan = plan_local_model_selection(profile(), manifest(candidate()))
    assert before == profile().to_dict()
    assert all(plan[key] is True for key in ("no_network_performed", "no_download_performed", "no_install_performed", "no_model_load_performed", "no_commissioning_performed", "no_authority_granted"))


def test_static_selection_boundary_verifier() -> None:
    from scripts.verify_local_model_selection_boundary import main
    assert main() == 0


def test_static_hardware_observation_boundary_verifier() -> None:
    from scripts.verify_local_inference_hardware_observation import main
    assert main() == 0


def test_static_execution_route_boundary_verifier() -> None:
    from scripts.verify_local_model_execution_routes import main
    assert main() == 0
