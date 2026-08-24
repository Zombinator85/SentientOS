"""Operator-confirmed, bounded selected-backend visibility verification.

The parent process never imports ``llama_cpp``.  The exact installation-bound
interpreter performs three read/query calls and no model or context operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from sentientos.local_runtime_dependencies import semantic_digest
from sentientos.local_runtime_import_verification import (
    authorization_for as import_authorization_for,
    compose_verification_plan as compose_import_plan,
    verify_runtime_import,
)
from sentientos.local_runtime_installation import verify_existing, verify_installation_sources

PLAN_SCHEMA = "sentientos.local_runtime_backend_verification_plan:v1"
AUTHORIZATION_SCHEMA = "sentientos.local_runtime_backend_verification_authorization:v1"
RECEIPT_SCHEMA = "sentientos.local_runtime_backend_verification_receipt:v1"
ACTION = "verify_selected_local_runtime_backend"
SENTINEL = "SENTIENTOS_RUNTIME_BACKEND_RESULT="
MAX_SYSTEM_INFO = 65536
TIMEOUT_SECONDS = 60
EXPECTED_REGISTRY = {("cpu", "cpu"): "CPU", ("cuda", "cu124"): "CUDA",
                     ("rocm", "rocm72"): "ROCm", ("rocm", "hip-radeon"): "ROCm",
                     ("metal", "metal"): "MTL"}
ACCELERATORS = ("CUDA", "ROCm", "MTL", "Vulkan", "SYCL", "OpenCL", "CANN", "MUSA")


class RuntimeBackendVerificationError(RuntimeError):
    def __init__(self, code: str, diagnostic: str = ""):
        self.code, self.diagnostic = code, diagnostic[:2048]
        super().__init__(code)


def _canonical_import_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(receipt)
    if value.get("status") == "already_verified_current":
        value["status"] = "runtime_import_verified"
    return value


def _native_manifest(import_plan: Mapping[str, Any]) -> dict[str, Any]:
    files = [dict(item) for item in import_plan["runtime_import_source_manifest"]["files"]
             if str(item["relative_path"]).startswith("llama_cpp/lib/")]
    files.sort(key=lambda item: item["relative_path"])
    if not files:
        raise RuntimeBackendVerificationError("runtime_backend_native_manifest_mismatch")
    return {"files": files}


def compose_verification_plan(installation_plan: Mapping[str, Any],
        installation_receipt: Mapping[str, Any], import_plan: Mapping[str, Any],
        import_receipt: Mapping[str, Any], receipt_root: Path | str) -> dict[str, Any]:
    expected_import = compose_import_plan(installation_plan, installation_receipt,
                                          import_plan["verification_receipt_root"])
    canonical = _canonical_import_receipt(import_receipt)
    if (dict(import_plan) != expected_import or canonical.get("status") != "runtime_import_verified" or
            canonical.get("runtime_import_verification_plan_digest") != import_plan.get("runtime_import_verification_plan_digest") or
            canonical.get("runtime_import_source_manifest_digest") != import_plan.get("runtime_import_source_manifest_digest") or
            canonical.get("runtime_available_for_import") is not True):
        raise RuntimeBackendVerificationError("runtime_backend_import_not_verified")
    key = (str(installation_plan["backend_family"]), str(installation_plan["backend_variant"]))
    if key not in EXPECTED_REGISTRY:
        raise RuntimeBackendVerificationError("runtime_backend_registry_mismatch")
    native = _native_manifest(import_plan)
    value = {"schema_version": PLAN_SCHEMA, "status": "runtime_backend_verification_planned",
        **{k: installation_plan[k] for k in ("installation_plan_digest", "runtime_id", "engine",
            "backend_family", "backend_variant", "environment_profile_digest")},
        "installation_receipt_semantic_digest": installation_receipt["receipt_semantic_digest"],
        "runtime_import_verification_plan_digest": import_plan["runtime_import_verification_plan_digest"],
        "runtime_import_source_manifest_digest": import_plan["runtime_import_source_manifest_digest"],
        "runtime_import_verification_receipt_semantic_digest": canonical["receipt_semantic_digest"],
        "installed_environment_path": import_plan["installed_environment_path"],
        "venv_interpreter_path": import_plan["venv_interpreter_path"],
        "venv_interpreter_identity": import_plan["venv_interpreter_identity"],
        "expected_package_root": import_plan["expected_package_root"],
        "expected_selected_backend_registry": EXPECTED_REGISTRY[key],
        "external_prerequisite_codes": list(installation_plan.get("external_prerequisite_codes", [])),
        "runtime_backend_native_manifest": native,
        "runtime_backend_native_manifest_digest": semantic_digest(native),
        "verification_receipt_root": str(Path(receipt_root).absolute())}
    value["runtime_backend_verification_plan_digest"] = semantic_digest(value)
    return value


def authorization_for(plan: Mapping[str, Any], *, operator_confirmed: bool) -> dict[str, Any]:
    keys = ("runtime_backend_verification_plan_digest", "installation_plan_digest",
            "runtime_import_verification_plan_digest", "runtime_import_verification_receipt_semantic_digest",
            "runtime_backend_native_manifest_digest", "runtime_id", "backend_family", "backend_variant",
            "expected_selected_backend_registry", "venv_interpreter_path", "installed_environment_path")
    value = {"schema_version": AUTHORIZATION_SCHEMA, "action": ACTION,
             **{key: plan[key] for key in keys}, "operator_confirmed": operator_confirmed}
    value["authorization_digest"] = semantic_digest(value)
    return value


def sanitized_backend_environment() -> dict[str, str]:
    remove = {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONSTARTUP", "PYTHONINSPECT",
              "LLAMA_CPP_LIB_PATH", "VIRTUAL_ENV", "CONDA_PREFIX", "GGML_CUDA_DEVICES",
              "GGML_METAL_DEVICES"}
    env = {k: v for k, v in os.environ.items()
           if k not in remove and not k.startswith(("PIP_", "UV_", "POETRY_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


_HELPER = r'''import hashlib,json
P="SENTIENTOS_RUNTIME_BACKEND_RESULT="
try:
 import llama_cpp
 import llama_cpp.llama_cpp as low
 gpu=bool(low.llama_supports_gpu_offload())
 rpc=bool(low.llama_supports_rpc())
 raw=low.llama_print_system_info()
 if isinstance(raw,bytes): raw=raw.decode("utf-8","strict")
 if not isinstance(raw,str): raise TypeError("system info is not text")
 encoded=raw.encode("utf-8","strict")
 if not encoded or len(encoded)>65536 or "\x00" in raw: raise ValueError("invalid system info")
 out={"ok":True,"gpu_offload_supported":gpu,"rpc_supported":rpc,"system_info":raw,"system_info_sha256":hashlib.sha256(encoded).hexdigest()}
except Exception as e:
 out={"ok":False,"error_type":type(e).__name__,"diagnostic":str(e)[:1024]}
print(P+json.dumps(out,sort_keys=True,separators=(",",":")))
'''


def _parse(stdout: str) -> dict[str, Any]:
    rows = [line[len(SENTINEL):] for line in stdout.splitlines() if line.startswith(SENTINEL)]
    if len(rows) != 1:
        raise RuntimeBackendVerificationError("runtime_backend_result_invalid")
    try:
        value = json.loads(rows[0])
    except json.JSONDecodeError as exc:
        raise RuntimeBackendVerificationError("runtime_backend_result_invalid") from exc
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise RuntimeBackendVerificationError("runtime_backend_result_invalid", str(value.get("diagnostic", "")))
    info = value.get("system_info")
    if not isinstance(info, str) or not info or "\x00" in info or len(info.encode()) > MAX_SYSTEM_INFO:
        raise RuntimeBackendVerificationError("runtime_backend_result_invalid")
    if value.get("system_info_sha256") != hashlib.sha256(info.encode()).hexdigest():
        raise RuntimeBackendVerificationError("runtime_backend_result_invalid")
    return value


def _registries(info: str) -> list[str]:
    # Pinned llama.cpp prints registry identifiers in backend feature lines.
    found: list[str] = []
    for name in ("CPU",) + ACCELERATORS:
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", info, re.I):
            canonical = next(x for x in ("CPU",) + ACCELERATORS if x.lower() == name.lower())
            if canonical not in found:
                found.append(canonical)
    if not found:
        raise RuntimeBackendVerificationError("runtime_backend_result_invalid")
    return found


def verify_runtime_backend(plan: Mapping[str, Any], installation_plan: Mapping[str, Any],
        installation_receipt: Mapping[str, Any], import_plan: Mapping[str, Any],
        import_receipt: Mapping[str, Any], *, authorization: Mapping[str, Any] | None = None,
        execute: bool = False, timeout_seconds: int = TIMEOUT_SECONDS, runner: Any = subprocess.run) -> dict[str, Any]:
    if not execute:
        return {"status": "inspection_ready", "runtime_backend_verification_plan_digest":
                plan["runtime_backend_verification_plan_digest"], "backend_query_performed": False}
    paths = [Path(str(x["verified_source_path"])) for x in installation_plan["artifacts"]]
    try:
        verify_installation_sources(installation_plan, paths)
        current_install = verify_existing(installation_plan, paths)
        fresh_import_plan = compose_import_plan(installation_plan, current_install, import_plan["verification_receipt_root"])
        fresh_import = verify_runtime_import(fresh_import_plan, installation_plan, current_install,
            authorization=import_authorization_for(fresh_import_plan, operator_confirmed=True), execute=True)
        expected = compose_verification_plan(installation_plan, current_install, fresh_import_plan,
                                             fresh_import, plan["verification_receipt_root"])
    except Exception as exc:
        if isinstance(exc, RuntimeBackendVerificationError): raise
        raise RuntimeBackendVerificationError("runtime_backend_import_not_verified") from exc
    if dict(plan) != expected:
        raise RuntimeBackendVerificationError("runtime_backend_authorization_invalid")
    expected_auth = authorization_for(expected, operator_confirmed=True)
    if authorization is None or dict(authorization) != expected_auth:
        raise RuntimeBackendVerificationError("runtime_backend_authorization_invalid")
    env_root = Path(plan["installed_environment_path"])
    before = semantic_digest(__import__("sentientos.local_runtime_import_verification", fromlist=["_environment_manifest"])._environment_manifest(env_root))
    try:
        with tempfile.TemporaryDirectory(prefix="sentientos-backend-verification-") as safe_cwd:
            run = runner([plan["venv_interpreter_path"], "-I", "-B", "-c", _HELPER], cwd=safe_cwd,
                         env=sanitized_backend_environment(), text=True, capture_output=True,
                         check=False, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeBackendVerificationError("runtime_backend_verification_timeout") from exc
    if run.returncode:
        raise RuntimeBackendVerificationError("runtime_backend_probe_failed", str(run.stderr)[-2048:])
    result = _parse(run.stdout)
    observed = _registries(result["system_info"])
    expected_registry = plan["expected_selected_backend_registry"]
    if expected_registry not in observed:
        raise RuntimeBackendVerificationError("runtime_backend_registry_missing")
    if result.get("rpc_supported") is not False:
        raise RuntimeBackendVerificationError("runtime_backend_rpc_ambiguity")
    accelerators = [name for name in observed if name in ACCELERATORS]
    if expected_registry != "CPU":
        if result.get("gpu_offload_supported") is not True:
            raise RuntimeBackendVerificationError("runtime_backend_gpu_not_visible")
        if accelerators != [expected_registry]:
            raise RuntimeBackendVerificationError("runtime_backend_accelerator_ambiguous")
    post_install = verify_existing(installation_plan, paths)
    post_import = compose_import_plan(installation_plan, post_install, import_plan["verification_receipt_root"])
    post_native = _native_manifest(post_import)
    after = semantic_digest(__import__("sentientos.local_runtime_import_verification", fromlist=["_environment_manifest"])._environment_manifest(env_root))
    if (post_native != plan["runtime_backend_native_manifest"] or before != after or
            post_import != fresh_import_plan):
        raise RuntimeBackendVerificationError("runtime_backend_environment_mutated")
    receipt = {"schema_version": RECEIPT_SCHEMA, "status": "runtime_backend_verified",
        "runtime_backend_verification_plan_digest": plan["runtime_backend_verification_plan_digest"],
        "authorization_digest": expected_auth["authorization_digest"],
        **{k: plan[k] for k in ("installation_plan_digest", "installation_receipt_semantic_digest",
            "runtime_import_verification_plan_digest", "runtime_import_source_manifest_digest",
            "runtime_import_verification_receipt_semantic_digest", "runtime_backend_native_manifest_digest",
            "runtime_id", "engine", "backend_family", "backend_variant", "environment_profile_digest")},
        "expected_selected_backend_registry": expected_registry, "selected_backend": expected_registry,
        "ordered_observed_backend_registries": observed,
        "additional_accelerator_registries": accelerators if expected_registry == "CPU" else [],
        "gpu_offload_capability_checked": True, "gpu_offload_supported": result["gpu_offload_supported"],
        "rpc_capability_checked": True, "rpc_supported": False,
        "system_info_sha256": result["system_info_sha256"],
        "backend_runtime_visibility_verified": True, "backend_prerequisites_verified": True,
        "selected_backend_verified": True, "runtime_installed": True, "runtime_import_performed": True,
        "runtime_available_for_import": True, "native_runtime_library_loaded": True,
        "model_load_performed": False, "commissioning_performed": False, "inference_performed": False,
        "runtime_execution_authority_granted": False}
    receipt["receipt_semantic_digest"] = semantic_digest(receipt)
    return receipt
