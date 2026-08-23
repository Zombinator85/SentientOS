"""Operator-confirmed, exact-wheel, offline local runtime installation.

This boundary installs bytes already held in verified escrow.  It deliberately
does not import the runtime, inspect an accelerator, load a model, or commission
execution.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import venv
from email.parser import Parser
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.local_runtime_acquisition import AcquisitionError, verify_runtime_custody
from sentientos.local_runtime_dependencies import semantic_digest
from sentientos.local_runtime_dependency_acquisition import (
    DependencyAcquisitionError, verify_dependency_bundle_custody,
)

PLAN_SCHEMA = "sentientos.local_runtime_installation_plan:v1"
AUTHORIZATION_SCHEMA = "sentientos.local_runtime_installation_authorization:v1"
RECEIPT_SCHEMA = "sentientos.local_runtime_installation_receipt:v1"
ACTION = "install_local_runtime"
EXPECTED = (("typing-extensions", "4.16.0"), ("numpy", "2.2.6"),
            ("diskcache", "5.6.3"), ("jinja2", "3.1.6"),
            ("markupsafe", "3.0.3"), ("llama-cpp-python", "0.3.35"))
BOOTSTRAP = frozenset({"pip", "setuptools"})


class InstallationError(RuntimeError):
    def __init__(self, code: str): self.code = code; super().__init__(code)


def default_installation_root() -> Path:
    data = os.environ.get("SENTIENTOS_DATA_DIR")
    return (Path(data) if data else Path.home() / ".sentientos") / "runtime-environments"


def _canon(value: object) -> str: return str(value).lower().replace("_", "-")


def base_interpreter_identity() -> dict[str, Any]:
    return {"executable": str(Path(sys.executable).resolve()), "implementation": sys.implementation.name,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_major": sys.version_info.major, "python_minor": sys.version_info.minor,
            "soabi": sysconfig.get_config_var("SOABI") or ""}


def _profile_fields(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {key: profile.get(key) for key in ("python_implementation", "python_major", "python_minor",
        "python_abi", "os_family", "architecture", "libc_family", "libc_version", "macos_version")}


def compose_installation_plan(runtime_plan: Mapping[str, Any], runtime_custody: Mapping[str, Any],
        dependency_plan: Mapping[str, Any], dependency_custody: Mapping[str, Any],
        environment_profile: Mapping[str, Any], installation_root: Path | str,
        *, interpreter_identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compose a deterministic, mutation-free plan from already verified custody."""
    try:
        rr = runtime_custody["receipt"]; re = runtime_custody["entry"]
        dr = dependency_custody["receipt"]; entries = dependency_custody["entries"]
        if len(entries) != 5 or {(_canon(e["package_name"]), e["package_version"]) for e in entries} != set(EXPECTED[:5]):
            raise InstallationError("invalid_installation_plan")
        if (_canon(re["package_name"]), re["package_version"]) != EXPECTED[5]:
            raise InstallationError("invalid_installation_plan")
        identity = dict(interpreter_identity or base_interpreter_identity())
        artifacts = [{"artifact_id": e["artifact_id"], "package": e["package_name"],
            "version": e["package_version"], "filename": e["artifact_filename"],
            "sha256": e["artifact_sha256"], "size": e["artifact_size_bytes"],
            "source_content_address": f"sha256:{e['artifact_sha256']}"} for e in entries]
        artifacts.append({"artifact_id": runtime_plan["runtime_id"], "package": re["package_name"],
            "version": re["package_version"], "filename": re["artifact_filename"],
            "sha256": re["artifact_sha256"], "size": re["artifact_size_bytes"],
            "source_content_address": f"sha256:{re['artifact_sha256']}"})
        plan = {"schema_version": PLAN_SCHEMA, "status": "installation_planned",
            **{k: runtime_plan[k] for k in ("runtime_id", "engine", "backend_family", "backend_variant", "package_name", "package_version")},
            "runtime_provisioning_plan_digest": runtime_plan["provisioning_plan_digest"],
            "runtime_catalog_digest": runtime_plan["runtime_catalog_digest"],
            "runtime_artifact_acquisition_receipt_semantic_digest": rr["receipt_semantic_digest"],
            "dependency_plan_digest": dependency_plan["dependency_plan_digest"],
            "dependency_catalog_digest": dependency_plan["dependency_catalog_digest"],
            "bundle_digest": dependency_plan["bundle_digest"],
            "dependency_bundle_acquisition_receipt_semantic_digest": dr["receipt_semantic_digest"],
            "environment_profile_digest": dependency_plan["environment_profile_digest"],
            "environment": _profile_fields(environment_profile), "base_interpreter_identity": identity,
            "installation_root": str(Path(installation_root).expanduser().absolute()), "artifacts": artifacts}
        plan["installation_plan_digest"] = semantic_digest(plan)
        return plan
    except InstallationError: raise
    except (KeyError, TypeError) as exc: raise InstallationError("invalid_installation_plan") from exc


def authorization_for(plan: Mapping[str, Any], *, operator_confirmed: bool) -> dict[str, Any]:
    value = {"schema_version": AUTHORIZATION_SCHEMA, "action": ACTION,
        "installation_plan_digest": plan.get("installation_plan_digest"),
        "runtime_provisioning_plan_digest": plan.get("runtime_provisioning_plan_digest"),
        "runtime_acquisition_receipt_digest": plan.get("runtime_artifact_acquisition_receipt_semantic_digest"),
        "dependency_plan_digest": plan.get("dependency_plan_digest"),
        "dependency_bundle_receipt_digest": plan.get("dependency_bundle_acquisition_receipt_semantic_digest"),
        "environment_profile_digest": plan.get("environment_profile_digest"),
        "ordered_artifact_sha256_values": [a.get("sha256") for a in plan.get("artifacts", [])],
        "installation_root": plan.get("installation_root"), "operator_confirmed": operator_confirmed}
    value["authorization_digest"] = semantic_digest(value); return value


def validate_plan(plan: Mapping[str, Any]) -> None:
    copy = dict(plan); claimed = copy.pop("installation_plan_digest", None)
    arts = plan.get("artifacts")
    if (plan.get("schema_version") != PLAN_SCHEMA or claimed != semantic_digest(copy) or
            not isinstance(arts, list) or len(arts) != 6 or
            {(_canon(a.get("package")), a.get("version")) for a in arts[:5]} != set(EXPECTED[:5]) or
            (_canon(arts[5].get("package")), arts[5].get("version")) != EXPECTED[5]):
        raise InstallationError("invalid_installation_plan")


def verify_environment_compatibility(plan: Mapping[str, Any], observed: Mapping[str, Any]) -> None:
    expected = plan.get("environment", {})
    pairs = (("python_implementation", "environment_profile_mismatch"), ("python_major", "environment_profile_mismatch"),
        ("python_minor", "environment_profile_mismatch"), ("python_abi", "environment_profile_mismatch"),
        ("os_family", "environment_profile_mismatch"), ("architecture", "environment_profile_mismatch"))
    if any(_canon(expected.get(k)) != _canon(observed.get(k)) for k, _ in pairs):
        raise InstallationError("environment_profile_mismatch")
    def version(v: object) -> tuple[int, ...]: return tuple(int(x) for x in str(v).split(".") if x != "")
    if expected.get("libc_version") and version(observed.get("libc_version")) < version(expected["libc_version"]):
        raise InstallationError("environment_profile_mismatch")
    if expected.get("macos_version") and version(observed.get("macos_version")) < version(expected["macos_version"]):
        raise InstallationError("environment_profile_mismatch")


def build_offline_pip_argv(venv_python: Path | str, wheel_paths: Sequence[Path | str]) -> list[str]:
    paths = [Path(p) for p in wheel_paths]
    if len(paths) != 6 or any(not p.is_absolute() or p.suffix != ".whl" or not p.is_file() for p in paths):
        raise InstallationError("invalid_installation_plan")
    return [str(Path(venv_python).absolute()), "-I", "-m", "pip", "--isolated", "install", "--no-index",
        "--no-deps", "--no-cache-dir", "--disable-pip-version-check", "--no-compile", "--no-input",
        *map(str, paths)]


def sanitized_environment() -> dict[str, str]:
    denied = ("PYTHONPATH", "PYTHONHOME", "PIP_")
    return {k: v for k, v in os.environ.items() if not any(k == x or k.startswith(x) for x in denied)}


_METADATA_CODE = """import importlib.metadata as m,json,sys,sysconfig
print(json.dumps({'executable':sys.executable,'python_version':sys.version.split()[0],'soabi':sysconfig.get_config_var('SOABI') or '',
'distributions':[{'name':d.metadata['Name'],'version':d.version,'path':str(d._path)} for d in m.distributions()]}))
"""


def inspect_installed(venv_python: Path) -> dict[str, Any]:
    run = subprocess.run([str(venv_python), "-I", "-c", _METADATA_CODE], env=sanitized_environment(),
        text=True, capture_output=True, check=False, timeout=60)
    if run.returncode: raise InstallationError("installed_metadata_verification_failed")
    try:
        loaded = json.loads(run.stdout)
        if not isinstance(loaded, dict): raise json.JSONDecodeError("object required", run.stdout, 0)
        result: dict[str, Any] = loaded
    except json.JSONDecodeError as exc: raise InstallationError("installed_metadata_verification_failed") from exc
    found = {_canon(d["name"]): d["version"] for d in result["distributions"]}
    for name, version in EXPECTED:
        if found.get(name) != version: raise InstallationError("installed_version_mismatch")
    unexpected = set(found) - {n for n, _ in EXPECTED} - BOOTSTRAP
    if unexpected: raise InstallationError("unexpected_installed_distribution")
    result["bootstrap_distributions"] = [{"name": n, "version": found[n]} for n in sorted(set(found) & BOOTSTRAP)]
    return result


def verify_records(environment: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    root = environment.resolve(); checked = []
    wanted = {n: v for n, v in EXPECTED}
    for dist in metadata["distributions"]:
        name = _canon(dist["name"])
        if name not in wanted: continue
        info = Path(dist["path"]); record = info / "RECORD"; meta = info / "METADATA"
        if not record.is_file(): raise InstallationError("installed_record_missing")
        message = Parser().parsestr(meta.read_text(encoding="utf-8")) if meta.is_file() else None
        if message is None or _canon(message["Name"]) != name or message["Version"] != wanted[name]:
            raise InstallationError("installed_version_mismatch")
        with record.open(newline="", encoding="utf-8") as stream:
            for relative, encoded_hash, encoded_size in csv.reader(stream):
                target = (info.parent / relative).resolve()
                if target != root and root not in target.parents: raise InstallationError("installed_record_path_escape")
                if not target.is_file(): raise InstallationError("installed_record_missing")
                if encoded_size and target.stat().st_size != int(encoded_size): raise InstallationError("installed_record_size_mismatch")
                if encoded_hash:
                    algorithm, value = encoded_hash.split("=", 1)
                    if algorithm != "sha256": raise InstallationError("installed_record_hash_mismatch")
                    observed = base64.urlsafe_b64encode(hashlib.sha256(target.read_bytes()).digest()).rstrip(b"=").decode()
                    if observed != value: raise InstallationError("installed_record_hash_mismatch")
        checked.append(name)
    return {"status": "record_verified", "verified_distributions": sorted(checked), "count": len(checked)}


def receipt_semantic_digest(receipt: Mapping[str, Any]) -> str:
    return semantic_digest({k: v for k, v in receipt.items() if k not in {"receipt_semantic_digest", "installed_at"}})


def install(plan: Mapping[str, Any], *, wheel_paths: Sequence[Path | str], observed_environment: Mapping[str, Any],
            authorization: Mapping[str, Any] | None = None, execute: bool = False) -> dict[str, Any]:
    validate_plan(plan); verify_environment_compatibility(plan, observed_environment)
    root = Path(str(plan["installation_root"])); final = root / str(plan["installation_plan_digest"])
    inspection = {"status": "inspection_ready", "installation_plan_digest": plan["installation_plan_digest"],
        "final_path": str(final), "network_performed": False, "download_performed": False,
        "package_install_performed": False}
    if not execute: return inspection
    expected_auth = authorization_for(plan, operator_confirmed=True)
    if authorization is None or dict(authorization) != expected_auth: raise InstallationError("installation_authorization_invalid")
    if dict(plan["base_interpreter_identity"]) != base_interpreter_identity(): raise InstallationError("base_interpreter_mismatch")
    paths = [Path(p).resolve() for p in wheel_paths]
    argv_probe = build_offline_pip_argv(Path(sys.executable), paths)
    del argv_probe
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if final.exists(): return verify_existing(plan, paths)
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=root)); environment = staging / "environment"
    try:
        try: venv.EnvBuilder(with_pip=True, system_site_packages=False, clear=False, upgrade=False).create(environment)
        except Exception as exc: raise InstallationError("venv_creation_failed") from exc
        vpy = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        argv = build_offline_pip_argv(vpy, paths)
        run = subprocess.run(argv, env=sanitized_environment(), text=True, capture_output=True, check=False, timeout=600)
        if run.returncode: raise InstallationError("offline_pip_failed")
        installed = inspect_installed(vpy); records = verify_records(environment, installed)
        receipt = {"schema_version": RECEIPT_SCHEMA, "status": "installed_verified",
            "installation_plan_digest": plan["installation_plan_digest"], "authorization_digest": expected_auth["authorization_digest"],
            **{k: plan[k] for k in ("runtime_id", "engine", "backend_family", "backend_variant", "environment_profile_digest",
                "runtime_provisioning_plan_digest", "runtime_artifact_acquisition_receipt_semantic_digest",
                "dependency_plan_digest", "bundle_digest", "dependency_bundle_acquisition_receipt_semantic_digest")},
            "artifacts": plan["artifacts"], "installation_relative_path": plan["installation_plan_digest"],
            "base_interpreter_identity": plan["base_interpreter_identity"],
            "venv_interpreter_identity": {k: installed[k] for k in ("executable", "python_version", "soabi")},
            "pip_bootstrap_version": next(d["version"] for d in installed["bootstrap_distributions"] if d["name"] == "pip"),
            "installed_distributions": installed["distributions"], "bootstrap_distributions": installed["bootstrap_distributions"],
            "record_verification": records, "network_performed": False, "download_performed": False,
            "dependency_resolution_performed": False, "package_install_performed": True, "runtime_installed": True,
            "runtime_import_performed": False, "runtime_available_for_import": False, "model_load_performed": False,
            "commissioning_performed": False, "runtime_execution_authority_granted": False}
        receipt["receipt_semantic_digest"] = receipt_semantic_digest(receipt)
        rp = staging / "installation-receipt.json"
        with rp.open("x", encoding="utf-8") as out:
            json.dump(receipt, out, sort_keys=True, separators=(",", ":")); out.write("\n"); out.flush(); os.fsync(out.fileno())
        try: staging.rename(final)
        except OSError:
            if not final.exists(): raise InstallationError("installation_publication_conflict")
            shutil.rmtree(staging); return verify_existing(plan, paths)
        fd = os.open(root, os.O_RDONLY); os.fsync(fd); os.close(fd)
        return receipt
    finally:
        if staging.exists(): shutil.rmtree(staging)


def verify_existing(plan: Mapping[str, Any], wheel_paths: Sequence[Path | str]) -> dict[str, Any]:
    final = Path(str(plan["installation_root"])) / str(plan["installation_plan_digest"])
    try:
        receipt = json.loads((final / "installation-receipt.json").read_text(encoding="utf-8"))
        if receipt.get("receipt_semantic_digest") != receipt_semantic_digest(receipt): raise ValueError
        if any(receipt.get(k) is not False for k in ("runtime_import_performed", "runtime_available_for_import",
                "model_load_performed", "commissioning_performed", "runtime_execution_authority_granted")): raise ValueError
        for path, artifact in zip(wheel_paths, plan["artifacts"]):
            p = Path(path)
            if p.stat().st_size != artifact["size"] or hashlib.sha256(p.read_bytes()).hexdigest() != artifact["sha256"]: raise ValueError
        env = final / "environment"; cfg = (env / "pyvenv.cfg").read_text(encoding="utf-8").lower()
        if "include-system-site-packages = false" not in cfg: raise ValueError
        vpy = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        installed = inspect_installed(vpy); verify_records(env, installed)
    except (OSError, ValueError, KeyError, InstallationError) as exc:
        raise InstallationError("installation_target_conflict") from exc
    result = dict(receipt); result["status"] = "already_installed_verified"; return result


def reverify_and_compose(*, runtime_plan: Mapping[str, Any], runtime_catalog_path: Path | str,
        runtime_escrow_root: Path | str, dependency_plan: Mapping[str, Any], dependency_catalog: Mapping[str, Any],
        dependency_escrow_root: Path | str, environment_profile: Mapping[str, Any],
        installation_root: Path | str) -> tuple[dict[str, Any], list[Path]]:
    try: runtime = verify_runtime_custody(runtime_plan, catalog_path=runtime_catalog_path, escrow_root=runtime_escrow_root)
    except AcquisitionError as exc: raise InstallationError("runtime_custody_not_verified") from exc
    try: deps = verify_dependency_bundle_custody(dependency_plan, catalog=dependency_catalog, escrow_root=dependency_escrow_root)
    except DependencyAcquisitionError as exc: raise InstallationError("dependency_bundle_not_verified") from exc
    plan = compose_installation_plan(runtime_plan, runtime, dependency_plan, deps, environment_profile, installation_root)
    return plan, [*deps["wheel_paths"], runtime["wheel_path"]]
