"""Operator-confirmed, bounded selected-backend visibility verification.

The parent process never imports ``llama_cpp``.  The exact installation-bound
interpreter performs three read/query calls and no model or context operation.
"""
from __future__ import annotations

import hashlib
import json
import os
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
    claimed = value.pop("receipt_semantic_digest", None)
    if claimed != semantic_digest(value):
        raise RuntimeBackendVerificationError("runtime_backend_import_not_verified")
    value["receipt_semantic_digest"] = claimed
    return value


def _native_manifest(import_plan: Mapping[str, Any]) -> dict[str, Any]:
    files = [dict(item) for item in import_plan["runtime_import_source_manifest"]["files"]
             if str(item["relative_path"]).startswith("llama_cpp/lib/")]
    files.sort(key=lambda item: item["relative_path"])
    if not files:
        raise RuntimeBackendVerificationError("runtime_backend_native_manifest_mismatch")
    return {"files": files}


def _validate_provisioning(runtime_plan: Mapping[str, Any], installation_plan: Mapping[str, Any]) -> None:
    copy = dict(runtime_plan)
    claimed = copy.pop("provisioning_plan_digest", None)
    shared = ("runtime_id", "engine", "backend_family", "backend_variant", "package_name", "package_version")
    if (runtime_plan.get("status") != "selected" or claimed != semantic_digest(copy) or
            claimed != installation_plan.get("runtime_provisioning_plan_digest") or
            any(runtime_plan.get(key) != installation_plan.get(key) for key in shared) or
            runtime_plan.get("environment_profile_digest") != installation_plan.get("environment_profile_digest") or
            not isinstance(runtime_plan.get("external_prerequisite_codes"), (list, tuple))):
        raise RuntimeBackendVerificationError("runtime_backend_provisioning_mismatch")


def compose_verification_plan(runtime_provisioning_plan: Mapping[str, Any], installation_plan: Mapping[str, Any],
        installation_receipt: Mapping[str, Any], import_plan: Mapping[str, Any],
        import_receipt: Mapping[str, Any], receipt_root: Path | str) -> dict[str, Any]:
    _validate_provisioning(runtime_provisioning_plan, installation_plan)
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
        "runtime_provisioning_plan_digest": runtime_provisioning_plan["provisioning_plan_digest"],
        "catalog_external_prerequisite_codes": list(runtime_provisioning_plan["external_prerequisite_codes"]),
        "runtime_backend_native_manifest": native,
        "runtime_backend_native_manifest_digest": semantic_digest(native),
        "verification_receipt_root": str(Path(receipt_root).absolute())}
    value["runtime_backend_verification_plan_digest"] = semantic_digest(value)
    return value


def authorization_for(plan: Mapping[str, Any], *, operator_confirmed: bool) -> dict[str, Any]:
    keys = ("runtime_backend_verification_plan_digest", "installation_plan_digest",
            "runtime_import_verification_plan_digest", "runtime_import_verification_receipt_semantic_digest",
            "runtime_backend_native_manifest_digest", "runtime_id", "backend_family", "backend_variant",
            "expected_selected_backend_registry", "venv_interpreter_path", "installed_environment_path",
            "runtime_provisioning_plan_digest", "catalog_external_prerequisite_codes")
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
    """Parse pinned llama.cpp ``REGISTRY : key = value | ...`` records only."""
    found: list[str] = []
    active = False
    for feature in info.replace("\r\n", "\n").replace("\n", " | ").split(" | "):
        if not feature:
            continue
        head, separator, tail = feature.partition(" : ")
        if separator:
            if (not head or len(head) > 64 or
                    not head.replace("_", "").replace("-", "").isalnum() or " = " not in tail):
                raise RuntimeBackendVerificationError("runtime_backend_result_invalid")
            if head not in found:
                found.append(head)
            active = True
        elif not active or " = " not in feature:
            raise RuntimeBackendVerificationError("runtime_backend_result_invalid")
    if not found:
        raise RuntimeBackendVerificationError("runtime_backend_result_invalid")
    return found


def validate_plan(plan: Mapping[str, Any]) -> None:
    copy = dict(plan); claimed = copy.pop("runtime_backend_verification_plan_digest", None)
    root = Path(str(plan.get("verification_receipt_root", "")))
    native = plan.get("runtime_backend_native_manifest")
    key = (str(plan.get("backend_family")), str(plan.get("backend_variant")))
    if (plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "runtime_backend_verification_planned" or
            claimed != semantic_digest(copy) or not root.is_absolute() or key not in EXPECTED_REGISTRY or
            plan.get("expected_selected_backend_registry") != EXPECTED_REGISTRY.get(key) or
            semantic_digest(native) != plan.get("runtime_backend_native_manifest_digest") or
            not isinstance(plan.get("catalog_external_prerequisite_codes"), list) or
            not all(Path(str(plan.get(k, ""))).is_absolute() for k in ("installed_environment_path", "venv_interpreter_path", "expected_package_root"))):
        raise RuntimeBackendVerificationError("runtime_backend_plan_invalid")


def _publish(plan: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    root = Path(plan["verification_receipt_root"])
    destination_dir = root / plan["runtime_backend_verification_plan_digest"]
    target = destination_dir / "runtime-backend-verification-receipt.json"
    for path in (*root.parents, root, destination_dir, target):
        if path.is_symlink(): raise RuntimeBackendVerificationError("runtime_backend_receipt_path_unsafe")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination_dir.mkdir(mode=0o700, exist_ok=True)
    payload = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if target.exists():
        if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
            raise RuntimeBackendVerificationError("runtime_backend_receipt_conflict")
        return True
    fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=destination_dir)
    existed = False
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        try: os.link(temporary, target)
        except FileExistsError:
            if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
                raise RuntimeBackendVerificationError("runtime_backend_receipt_conflict")
            existed = True
        directory_fd = os.open(destination_dir, os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
    return existed


def verify_runtime_backend(plan: Mapping[str, Any], runtime_provisioning_plan: Mapping[str, Any], installation_plan: Mapping[str, Any],
        installation_receipt: Mapping[str, Any], import_plan: Mapping[str, Any],
        import_receipt: Mapping[str, Any], *, authorization: Mapping[str, Any] | None = None,
        execute: bool = False, timeout_seconds: int = TIMEOUT_SECONDS, runner: Any = subprocess.run) -> dict[str, Any]:
    validate_plan(plan)
    _validate_provisioning(runtime_provisioning_plan, installation_plan)
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
        expected = compose_verification_plan(runtime_provisioning_plan, installation_plan, current_install, fresh_import_plan,
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
    accelerators = [name for name in observed if name != "CPU"]
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
            "runtime_id", "engine", "backend_family", "backend_variant", "environment_profile_digest",
            "runtime_provisioning_plan_digest", "catalog_external_prerequisite_codes")},
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
    if _publish(plan, receipt):
        receipt = dict(receipt); receipt["status"] = "already_verified_current"
    return receipt
