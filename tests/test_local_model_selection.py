from __future__ import annotations

import copy

import pytest

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


def test_deterministic_host_profile_maps_only_explicit_inventory_facts() -> None:
    inventory = build_host_inventory_manifest(manifest_id="i", node_id="n", architecture="aarch64", os_family="linux",
        cpu_summary={"model": "AVX512 words are not evidence", "avx2": True}, ram_summary={"total_bytes": 8 * GIB},
        gpu_summary={"vendor": "NVIDIA"}, observed_at="fixed")
    first = hardware_profile_from_inventory(inventory)
    second = hardware_profile_from_inventory(inventory)
    assert first.digest == second.digest
    assert (first.architecture, first.avx, first.avx2, first.avx512) == ("aarch64", "unknown", True, "unknown")
    assert first.backend_family is None and first.vram_bytes is None


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
