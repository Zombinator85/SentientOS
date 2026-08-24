"""Bounded verification that an installed local runtime is importable.

This module deliberately stops at Python import and byte witnessing of the
already-loaded packaged library.  SentientOS makes no explicit backend,
capability, system-information, model, or inference call.  Importing upstream
llama-cpp-python necessarily executes its package initialization/native binding
code (including upstream initialization calls made by that package).
"""
from __future__ import annotations

import hashlib
import base64
import csv
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.local_runtime_dependencies import semantic_digest
from sentientos.local_runtime_installation import (
    InstallationError, receipt_semantic_digest, validate_plan,
    verify_existing, verify_installation_sources,
)

PLAN_SCHEMA = "sentientos.local_runtime_import_verification_plan:v1"
AUTHORIZATION_SCHEMA = "sentientos.local_runtime_import_verification_authorization:v1"
RECEIPT_SCHEMA = "sentientos.local_runtime_import_verification_receipt:v1"
ACTION = "verify_local_runtime_import"
EXPECTED_VERSION = "0.3.35"
SENTINEL = "SENTIENTOS_RUNTIME_IMPORT_RESULT="
TIMEOUT_SECONDS = 60


class RuntimeImportVerificationError(RuntimeError):
    def __init__(self, code: str, diagnostic: str = ""):
        self.code = code
        self.diagnostic = diagnostic[:2048]
        super().__init__(code)


def default_receipt_root() -> Path:
    data = Path(os.environ.get("SENTIENTOS_DATA_DIR", Path.home() / ".sentientos"))
    return data / "runtime-verifications" / "import"


def _environment_path(installation_plan: Mapping[str, Any]) -> Path:
    return (Path(str(installation_plan["installation_root"])) /
            str(installation_plan["installation_plan_digest"]) / "environment").absolute()


def _interpreter(environment: Path) -> Path:
    return (environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")).absolute()


def _file_identity(path: Path, relative: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {"relative_path": relative, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def _import_source_manifest(environment: Path, dist_info: Path) -> dict[str, Any]:
    """Read RECORD and bind its hash-custodied distribution files."""
    root = environment.resolve()
    site = dist_info.parent.resolve()
    record = dist_info / "RECORD"
    files: list[dict[str, Any]] = []
    try:
        with record.open(newline="", encoding="utf-8") as stream:
            for relative, encoded_hash, encoded_size in csv.reader(stream):
                if not encoded_hash or not encoded_size:
                    continue
                target = (site / relative).resolve(strict=True)
                if target != root and root not in target.parents:
                    raise RuntimeImportVerificationError("installation_not_verified")
                algorithm, encoded = encoded_hash.split("=", 1)
                expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).hex()
                identity = _file_identity(target, relative)
                if algorithm != "sha256" or identity["size"] != int(encoded_size) or identity["sha256"] != expected:
                    raise RuntimeImportVerificationError("installation_not_verified")
                files.append(identity)
    except (OSError, ValueError) as exc:
        raise RuntimeImportVerificationError("installation_not_verified") from exc
    files.sort(key=lambda item: item["relative_path"])
    required = {"llama_cpp/__init__.py", "llama_cpp/llama_cpp.py"}
    paths = {item["relative_path"] for item in files}
    native = [p for p in paths if p.startswith("llama_cpp/lib/") and Path(p).name in
              {"libllama.so", "libllama.dylib", "llama.dll", "libllama.dll"}]
    if not required.issubset(paths) or len(native) != 1:
        raise RuntimeImportVerificationError("installation_not_verified")
    return {"record_relative_path": str(record.resolve().relative_to(root)).replace(os.sep, "/"),
            "files": files, "selected_native_library_relative_path": native[0]}


def _environment_manifest(root: Path) -> dict[str, dict[str, Any]]:
    """Witness environment contents and topology without following symlinks."""
    manifest: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root)).replace(os.sep, "/")
        if path.is_symlink():
            manifest[relative] = {"entry_type": "symlink", "relative_path": relative,
                                  "link_target": os.readlink(path)}
        elif path.is_file():
            identity = _file_identity(path, relative)
            manifest[relative] = {"entry_type": "regular_file", **identity}
        elif path.is_dir():
            manifest[relative] = {"entry_type": "directory", "relative_path": relative}
    return manifest


def _canonical_installation_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    canonical = dict(receipt)
    if canonical.get("status") == "already_installed_verified":
        canonical["status"] = "installed_verified"
    return canonical


def compose_verification_plan(installation_plan: Mapping[str, Any],
        installation_receipt: Mapping[str, Any], receipt_root: Path | str | None = None) -> dict[str, Any]:
    """Compose a deterministic inspection-only plan; no runtime import occurs."""
    try:
        validate_plan(installation_plan)
        required_false = ("runtime_import_performed", "runtime_available_for_import",
            "model_load_performed", "commissioning_performed", "runtime_execution_authority_granted")
        canonical_receipt = _canonical_installation_receipt(installation_receipt)
        # ``already_installed_verified`` describes the verification operation,
        # not a mutation of the immutable installation receipt.
        if (canonical_receipt.get("status") != "installed_verified" or
                installation_receipt.get("runtime_installed") is not True or
                any(installation_receipt.get(k) is not False for k in required_false) or
                installation_receipt.get("receipt_semantic_digest") != receipt_semantic_digest(canonical_receipt)):
            raise RuntimeImportVerificationError("installation_not_verified")
        env = _environment_path(installation_plan)
        vpy = _interpreter(env)
        identity = dict(canonical_receipt["venv_interpreter_identity"])
        identity["implementation"] = str(installation_plan["environment"]["python_implementation"])
        dist = next(d for d in installation_receipt["installed_distributions"]
                    if str(d["name"]).lower().replace("_", "-") == "llama-cpp-python")
        package_root = (Path(str(dist["path"])).parent / "llama_cpp").absolute()
        manifest = _import_source_manifest(env, Path(str(dist["path"])))
        value = {"schema_version": PLAN_SCHEMA, "status": "runtime_import_verification_planned",
            "installation_plan_digest": installation_plan["installation_plan_digest"],
            "installation_receipt_semantic_digest": installation_receipt["receipt_semantic_digest"],
            **{k: installation_plan[k] for k in ("runtime_id", "engine", "backend_family", "backend_variant",
                "environment_profile_digest")},
            "runtime_package": "llama-cpp-python", "expected_runtime_version": EXPECTED_VERSION,
            "installed_environment_path": str(env), "venv_interpreter_path": str(vpy),
            "venv_interpreter_identity": identity, "expected_package_root": str(package_root),
            "runtime_import_source_manifest": manifest,
            "runtime_import_source_manifest_digest": semantic_digest(manifest),
            "verification_receipt_root": str(Path(receipt_root or default_receipt_root()).absolute())}
        value["runtime_import_verification_plan_digest"] = semantic_digest(value)
        return value
    except RuntimeImportVerificationError:
        raise
    except (InstallationError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise RuntimeImportVerificationError("installation_not_verified") from exc


def validate_verification_plan(plan: Mapping[str, Any]) -> None:
    copy = dict(plan); claimed = copy.pop("runtime_import_verification_plan_digest", None)
    env = Path(str(plan.get("installed_environment_path", "")))
    vpy = Path(str(plan.get("venv_interpreter_path", "")))
    root = Path(str(plan.get("expected_package_root", "")))
    if (plan.get("schema_version") != PLAN_SCHEMA or claimed != semantic_digest(copy) or
            plan.get("runtime_package") != "llama-cpp-python" or
            plan.get("expected_runtime_version") != EXPECTED_VERSION or
            not env.is_absolute() or not vpy.is_absolute() or not root.is_absolute() or
            vpy != _interpreter(env) or env not in root.parents or
            plan.get("runtime_import_source_manifest_digest") !=
            semantic_digest(plan.get("runtime_import_source_manifest"))):
        raise RuntimeImportVerificationError("runtime_import_result_invalid")


def authorization_for(plan: Mapping[str, Any], *, operator_confirmed: bool) -> dict[str, Any]:
    value = {"schema_version": AUTHORIZATION_SCHEMA, "action": ACTION,
        **{k: plan.get(k) for k in ("runtime_import_verification_plan_digest", "installation_plan_digest",
            "installation_receipt_semantic_digest", "runtime_id", "backend_family", "backend_variant",
            "venv_interpreter_path", "installed_environment_path")},
        "runtime_import_source_manifest_digest": plan.get("runtime_import_source_manifest_digest"),
        "operator_confirmed": operator_confirmed}
    value["authorization_digest"] = semantic_digest(value)
    return value


_HELPER = r'''import hashlib,importlib.metadata as m,json,pathlib,sys,sysconfig
P="SENTIENTOS_RUNTIME_IMPORT_RESULT="
try:
 import llama_cpp
 import llama_cpp.llama_cpp as low
 lib=pathlib.Path(str(low._lib._name)).resolve(strict=True)
 package=pathlib.Path(llama_cpp.__file__).resolve(strict=True); lowpath=pathlib.Path(low.__file__).resolve(strict=True); root=package.parent.parent
 def ident(path):
  h=hashlib.sha256(); size=0
  with path.open("rb") as f:
   while True:
    b=f.read(1048576)
    if not b: break
    size+=len(b); h.update(b)
  return {"relative_path":path.relative_to(root).as_posix(),"size":size,"sha256":h.hexdigest()}
 out={"ok":True,"executable":str(pathlib.Path(sys.executable).resolve()),"python_version":sys.version.split()[0],"implementation":sys.implementation.name,"soabi":sysconfig.get_config_var("SOABI") or "","package_version":str(llama_cpp.__version__),"distribution_version":m.version("llama-cpp-python"),"package_module_path":str(package),"low_level_module_path":str(lowpath),"native_library_path":str(lib),"native_library_filename":lib.name,"package_module_identity":ident(package),"low_level_module_identity":ident(lowpath),"native_library_identity":ident(lib),"llama_class_present":hasattr(llama_cpp,"Llama"),"backend_init_symbol_present":hasattr(low,"llama_backend_init"),"gpu_offload_query_symbol_present":hasattr(low,"llama_supports_gpu_offload")}
except Exception as e:
 out={"ok":False,"error_type":type(e).__name__,"diagnostic":str(e)[:1024]}
print(P+json.dumps(out,sort_keys=True,separators=(",",":")))
'''


def sanitized_import_environment() -> dict[str, str]:
    exact = {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONSTARTUP", "PYTHONINSPECT",
             "LLAMA_CPP_LIB_PATH", "VIRTUAL_ENV", "CONDA_PREFIX"}
    prefixes = ("PIP_", "UV_", "POETRY_")
    result = {k: v for k, v in os.environ.items() if k not in exact and not k.startswith(prefixes)}
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    return result


def _parse_probe(stdout: str) -> dict[str, Any]:
    lines = [line[len(SENTINEL):] for line in stdout.splitlines() if line.startswith(SENTINEL)]
    if len(lines) != 1:
        raise RuntimeImportVerificationError("runtime_import_result_invalid")
    try: result = json.loads(lines[0])
    except json.JSONDecodeError as exc: raise RuntimeImportVerificationError("runtime_import_result_invalid") from exc
    if not isinstance(result, dict): raise RuntimeImportVerificationError("runtime_import_result_invalid")
    return result


def _within(path: Path, parent: Path) -> bool:
    return path != parent and parent in path.parents


def _validate_probe(plan: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    if result.get("ok") is not True:
        raise RuntimeImportVerificationError("runtime_import_failed", str(result.get("diagnostic", "")))
    if result.get("package_version") != EXPECTED_VERSION or result.get("distribution_version") != EXPECTED_VERSION:
        raise RuntimeImportVerificationError("runtime_version_mismatch")
    env = Path(str(plan["installed_environment_path"])).resolve()
    package_root = Path(str(plan["expected_package_root"])).resolve()
    package = Path(str(result.get("package_module_path", "")))
    low = Path(str(result.get("low_level_module_path", "")))
    if (not package.is_absolute() or not low.is_absolute() or
            package.resolve() != (package_root / "__init__.py").resolve() or
            low.resolve() != (package_root / "llama_cpp.py").resolve()):
        raise RuntimeImportVerificationError("runtime_module_origin_mismatch")
    native = Path(str(result.get("native_library_path", "")))
    if not native.is_absolute() or native.is_symlink() or not native.is_file():
        raise RuntimeImportVerificationError("runtime_native_library_missing")
    lib_root = package_root / "lib"
    if not _within(native, env) or not _within(native, lib_root.resolve()):
        raise RuntimeImportVerificationError("runtime_native_library_origin_mismatch")
    names = {"libllama.so", "libllama.dylib", "llama.dll", "libllama.dll"}
    if native.name not in names:
        raise RuntimeImportVerificationError("runtime_native_library_identity_mismatch")
    expected = {item["relative_path"]: item for item in
                plan["runtime_import_source_manifest"]["files"]}
    observations = (result.get("package_module_identity"), result.get("low_level_module_identity"),
                    result.get("native_library_identity"))
    if any(not isinstance(item, dict) or expected.get(item.get("relative_path")) != item
           for item in observations):
        raise RuntimeImportVerificationError("runtime_import_source_identity_mismatch")
    package_observation = dict(result["package_module_identity"])
    low_observation = dict(result["low_level_module_identity"])
    native_observation = dict(result["native_library_identity"])
    if (package_observation.get("relative_path") != "llama_cpp/__init__.py" or
            low_observation.get("relative_path") != "llama_cpp/llama_cpp.py" or
            native_observation.get("relative_path") !=
            plan["runtime_import_source_manifest"]["selected_native_library_relative_path"] or
            result.get("native_library_filename") != native.name):
        raise RuntimeImportVerificationError("runtime_import_source_identity_mismatch")
    identity = plan["venv_interpreter_identity"]
    if (result.get("executable") != str(Path(str(plan["venv_interpreter_path"])).resolve()) or
            any(result.get(k) != identity.get(k) for k in ("python_version", "implementation", "soabi")) or
            any(result.get(k) is not True for k in ("llama_class_present", "backend_init_symbol_present",
                "gpu_offload_query_symbol_present"))):
        raise RuntimeImportVerificationError("runtime_import_result_invalid")


def _publish_receipt(plan: Mapping[str, Any], receipt: Mapping[str, Any]) -> str:
    root = Path(str(plan["verification_receipt_root"])) / str(plan["runtime_import_verification_plan_digest"])
    probe = root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    cursor = probe
    while True:
        if cursor.is_symlink() or not cursor.is_dir():
            raise RuntimeImportVerificationError("runtime_import_receipt_path_unsafe")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeImportVerificationError("runtime_import_receipt_path_unsafe")
    target = root / "runtime-import-verification-receipt.json"
    payload = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if target.exists():
        if target.is_symlink() or target.read_bytes() != payload:
            raise RuntimeImportVerificationError("runtime_import_receipt_path_unsafe")
        return "already_verified_current"
    fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=root)
    try:
        with os.fdopen(fd, "wb") as out: out.write(payload); out.flush(); os.fsync(out.fileno())
        try: os.link(temporary, target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != payload:
                raise RuntimeImportVerificationError("runtime_import_receipt_path_unsafe")
        directory = os.open(root, os.O_RDONLY); os.fsync(directory); os.close(directory)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
    return "runtime_import_verified"


def verify_runtime_import(plan: Mapping[str, Any], installation_plan: Mapping[str, Any],
        installation_receipt: Mapping[str, Any], *, authorization: Mapping[str, Any] | None = None,
        execute: bool = False, timeout_seconds: int = TIMEOUT_SECONDS,
        runner: Any = subprocess.run) -> dict[str, Any]:
    validate_verification_plan(plan)
    if not execute:
        return {"status": "inspection_ready", "runtime_import_verification_plan_digest":
                plan["runtime_import_verification_plan_digest"], "runtime_import_performed": False}
    try:
        validate_plan(installation_plan)
        paths = [Path(str(a["verified_source_path"])) for a in installation_plan["artifacts"]]
        verify_installation_sources(installation_plan, paths)
        current = verify_existing(installation_plan, paths)
        canonical_current = _canonical_installation_receipt(current)
        canonical_supplied = _canonical_installation_receipt(installation_receipt)
        if (canonical_current.get("receipt_semantic_digest") != receipt_semantic_digest(canonical_current) or
                canonical_supplied != canonical_current):
            raise InstallationError("installation_target_conflict")
        expected_plan = compose_verification_plan(
            installation_plan, canonical_current,
            receipt_root=str(plan["verification_receipt_root"]),
        )
        if dict(plan) != expected_plan:
            raise InstallationError("installation_target_conflict")
    except InstallationError as exc:
        raise RuntimeImportVerificationError("installation_not_verified") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeImportVerificationError("installation_not_verified") from exc
    expected_auth = authorization_for(expected_plan, operator_confirmed=True)
    if authorization is None or dict(authorization) != expected_auth:
        raise RuntimeImportVerificationError("runtime_import_authorization_invalid")
    vpy = Path(str(plan["venv_interpreter_path"])); env = Path(str(plan["installed_environment_path"])); cwd = env.parent
    before_environment = _environment_manifest(env)
    try:
        run = runner([str(vpy), "-I", "-B", "-c", _HELPER], env=sanitized_import_environment(),
            cwd=cwd, text=True, capture_output=True, check=False, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeImportVerificationError("runtime_import_timeout") from exc
    if run.returncode:
        raise RuntimeImportVerificationError("runtime_import_failed", str(run.stderr)[-2048:])
    result = _parse_probe(run.stdout); _validate_probe(plan, result)
    try:
        post = verify_existing(installation_plan, paths)
        canonical_post = _canonical_installation_receipt(post)
        post_expected_plan = compose_verification_plan(
            installation_plan, canonical_post,
            receipt_root=str(plan["verification_receipt_root"]),
        )
        if (canonical_post != canonical_current or post_expected_plan != expected_plan or
                _environment_manifest(env) != before_environment):
            raise InstallationError("installation_target_conflict")
    except InstallationError as exc:
        raise RuntimeImportVerificationError("installation_not_verified") from exc
    observed_identity = {k: result[k] for k in ("executable", "python_version", "implementation", "soabi")}
    package_identity = dict(result["package_module_identity"])
    low_identity = dict(result["low_level_module_identity"])
    native_identity = {**result["native_library_identity"], "filename": result["native_library_filename"]}
    receipt = {"schema_version": RECEIPT_SCHEMA, "status": "runtime_import_verified",
        "runtime_import_verification_plan_digest": plan["runtime_import_verification_plan_digest"],
        "runtime_import_source_manifest_digest": plan["runtime_import_source_manifest_digest"],
        "authorization_digest": expected_auth["authorization_digest"],
        **{k: plan[k] for k in ("installation_plan_digest", "installation_receipt_semantic_digest", "runtime_id",
            "engine", "backend_family", "backend_variant", "environment_profile_digest")},
        "venv_interpreter_identity": observed_identity,
        "package_module_identity": package_identity,
        "low_level_module_identity": low_identity,
        "native_library_identity": native_identity,
        "expected_package_version": EXPECTED_VERSION, "observed_package_version": result["package_version"],
        "observed_distribution_version": result["distribution_version"],
        **{k: result[k] for k in ("package_module_path", "low_level_module_path", "native_library_filename",
            "native_library_path", "llama_class_present",
            "backend_init_symbol_present", "gpu_offload_query_symbol_present")},
        "native_library_size": native_identity["size"], "native_library_sha256": native_identity["sha256"],
        "network_performed": False, "download_performed": False, "package_install_performed": False,
        "runtime_installed": True, "runtime_import_performed": True, "runtime_available_for_import": True,
        "native_runtime_library_loaded": True, "backend_prerequisites_verified": False,
        "selected_backend_verified": False, "gpu_offload_capability_checked": False,
        "model_load_performed": False, "commissioning_performed": False, "inference_performed": False,
        "runtime_execution_authority_granted": False}
    receipt["receipt_semantic_digest"] = semantic_digest(receipt)
    status = _publish_receipt(plan, receipt)
    return {**receipt, "status": status}
