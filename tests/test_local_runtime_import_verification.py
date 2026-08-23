from __future__ import annotations
import base64
import csv
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path
import pytest

from sentientos.local_runtime_dependencies import semantic_digest
from sentientos.local_runtime_import_verification import (RuntimeImportVerificationError,
    SENTINEL, authorization_for as import_authorization, compose_verification_plan,
    sanitized_import_environment, verify_runtime_import)
from sentientos.local_runtime_installation import (EXPECTED, authorization_for,
    base_interpreter_identity, install)

pytestmark = pytest.mark.no_legacy_skip

def _wheel(path: Path, name: str, version: str) -> None:
    dist = name.replace("-", "_"); info = f"{dist}-{version}.dist-info"
    init = b"MARKER=True\n"
    files = {f"{dist}/__init__.py": init,
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\n".encode(),
        f"{info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    if name == "llama-cpp-python":
        files = {"llama_cpp/__init__.py": b"from .llama_cpp import *\n__version__='0.3.35'\nclass Llama: pass\n",
            "llama_cpp/llama_cpp.py": b"from pathlib import Path\nclass FakeLib: pass\n_lib=FakeLib()\n_lib._name=str(Path(__file__).parent/'lib'/'libllama.so')\ndef llama_backend_init(): raise AssertionError('must not call')\ndef llama_supports_gpu_offload(): raise AssertionError('must not call')\n",
            "llama_cpp/lib/libllama.so": b"opaque-synthetic-native-library", **{k:v for k,v in files.items() if k.startswith(info)}}
    rows=[]
    for relative,data in files.items():
        digest=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        rows.append((relative,f"sha256={digest}",str(len(data))))
    rows.append((f"{info}/RECORD","","")); output=io.StringIO(); csv.writer(output,lineterminator="\n").writerows(rows)
    files[f"{info}/RECORD"]=output.getvalue().encode()
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_STORED) as archive:
        for relative,data in files.items(): archive.writestr(relative,data)

def _installed(tmp_path: Path):
    artifacts=[]; paths=[]
    for name,version in EXPECTED:
        path=(tmp_path/f"{name.replace('-','_')}-{version}-py3-none-any.whl").resolve(); _wheel(path,name,version)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append({"artifact_id":name,"package":name,"version":version,"filename":path.name,
            "sha256":digest,"size":path.stat().st_size,"source_content_address":f"sha256:{digest}",
            "verified_source_path":str(path)}); paths.append(path)
    environment={"python_implementation":"cpython","python_major":sys.version_info.major,
        "python_minor":sys.version_info.minor,"python_abi":f"cp{sys.version_info.major}{sys.version_info.minor}",
        "os_family":"linux","architecture":"x86_64","libc_family":"glibc","libc_version":"2.17","macos_version":""}
    plan={"schema_version":"sentientos.local_runtime_installation_plan:v1","status":"installation_planned",
        "runtime_id":"synthetic","engine":"llama.cpp","backend_family":"cpu","backend_variant":"cpu",
        "package_name":"llama-cpp-python","package_version":"0.3.35","runtime_provisioning_plan_digest":"a",
        "runtime_catalog_digest":"b","runtime_artifact_acquisition_receipt_semantic_digest":"c",
        "dependency_plan_digest":"d","dependency_catalog_digest":"e","bundle_digest":"f",
        "dependency_bundle_acquisition_receipt_semantic_digest":"g","environment_profile_digest":"h",
        "environment":environment,"base_interpreter_identity":base_interpreter_identity(),
        "installation_root":str(tmp_path/"environments"),"artifacts":artifacts}
    plan["installation_plan_digest"]=semantic_digest(plan)
    receipt=install(plan,wheel_paths=paths,observed_environment=environment,
        authorization=authorization_for(plan,operator_confirmed=True),execute=True)
    final=Path(plan["installation_root"])/plan["installation_plan_digest"]
    return plan,receipt,paths,final

def _snapshot(root: Path) -> dict[str,str]:
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}

def test_synthetic_installed_interpreter_imports_and_receipt_is_immutable(tmp_path):
    installation,receipt,_,final=_installed(tmp_path)
    plan=compose_verification_plan(installation,receipt,tmp_path/"receipts")
    before=_snapshot(final/"environment")
    result=verify_runtime_import(plan,installation,receipt,
        authorization=import_authorization(plan,operator_confirmed=True),execute=True)
    assert result["status"]=="runtime_import_verified"
    assert result["runtime_available_for_import"] is True
    assert result["native_library_sha256"]==hashlib.sha256(b"opaque-synthetic-native-library").hexdigest()
    assert result["runtime_execution_authority_granted"] is False
    assert before==_snapshot(final/"environment")
    again=verify_runtime_import(plan,installation,receipt,
        authorization=import_authorization(plan,operator_confirmed=True),execute=True)
    assert again["status"]=="already_verified_current"

def test_inspection_authorization_and_source_tamper_fail_closed(tmp_path):
    installation,receipt,paths,_=_installed(tmp_path)
    plan=compose_verification_plan(installation,receipt,tmp_path/"receipts")
    assert verify_runtime_import(plan,installation,receipt)["status"]=="inspection_ready"
    with pytest.raises(RuntimeImportVerificationError,match="runtime_import_authorization_invalid"):
        verify_runtime_import(plan,installation,receipt,execute=True)
    paths[0].write_bytes(b"altered")
    with pytest.raises(RuntimeImportVerificationError,match="installation_not_verified"):
        verify_runtime_import(plan,installation,receipt,
            authorization=import_authorization(plan,operator_confirmed=True),execute=True)

def test_probe_environment_strips_injection_and_preserves_loader_facts(monkeypatch):
    monkeypatch.setenv("PYTHONPATH","bad"); monkeypatch.setenv("LLAMA_CPP_LIB_PATH","bad")
    monkeypatch.setenv("LD_LIBRARY_PATH","real-loader")
    env=sanitized_import_environment()
    assert "PYTHONPATH" not in env and "LLAMA_CPP_LIB_PATH" not in env
    assert env["LD_LIBRARY_PATH"]=="real-loader" and env["PYTHONDONTWRITEBYTECODE"]=="1"

def test_timeout_nonzero_and_invalid_sentinel_are_bounded(tmp_path):
    installation,receipt,_,_=_installed(tmp_path); plan=compose_verification_plan(installation,receipt,tmp_path/"r")
    auth=import_authorization(plan,operator_confirmed=True)
    def timeout(*args,**kwargs): raise __import__("subprocess").TimeoutExpired(args[0],1)
    with pytest.raises(RuntimeImportVerificationError,match="runtime_import_timeout"):
        verify_runtime_import(plan,installation,receipt,authorization=auth,execute=True,runner=timeout)
    result=type("R",(),{"returncode":0,"stdout":SENTINEL+"{}\n"+SENTINEL+"{}\n","stderr":""})()
    with pytest.raises(RuntimeImportVerificationError,match="runtime_import_result_invalid"):
        verify_runtime_import(plan,installation,receipt,authorization=auth,execute=True,runner=lambda *a,**k:result)

def test_invalid_installation_receipt_is_rejected(tmp_path):
    installation,receipt,_,_=_installed(tmp_path); receipt=dict(receipt); receipt["runtime_installed"]=False
    with pytest.raises(RuntimeImportVerificationError,match="installation_not_verified"):
        compose_verification_plan(installation,receipt,tmp_path/"r")
