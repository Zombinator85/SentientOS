from pathlib import Path
import sys
import json
import pytest
from sentientos.local_runtime_installation import (InstallationError, EXPECTED, authorization_for,
    build_offline_pip_argv, install, receipt_semantic_digest, validate_plan)
from sentientos.local_runtime_dependencies import semantic_digest

pytestmark = pytest.mark.no_legacy_skip

def plan(tmp_path: Path):
    arts=[]; paths=[]
    for i,(name,version) in enumerate(EXPECTED):
        p=(tmp_path/f"{name.replace('-','_')}-{version}-py3-none-any.whl").resolve(); p.write_bytes(bytes([i]))
        import hashlib
        arts.append({"artifact_id":name,"package":name,"version":version,"filename":p.name,
            "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"size":1,"source_content_address":"sha256:x"}); paths.append(p)
    value={"schema_version":"sentientos.local_runtime_installation_plan:v1","status":"installation_planned",
        "runtime_id":"r","engine":"llama.cpp","backend_family":"cpu","backend_variant":"cpu",
        "package_name":"llama-cpp-python","package_version":"0.3.35","runtime_provisioning_plan_digest":"a",
        "runtime_catalog_digest":"b","runtime_artifact_acquisition_receipt_semantic_digest":"c",
        "dependency_plan_digest":"d","dependency_catalog_digest":"e","bundle_digest":"f",
        "dependency_bundle_acquisition_receipt_semantic_digest":"g","environment_profile_digest":"h",
        "environment":{"python_implementation":"cpython","python_major":sys.version_info.major,"python_minor":sys.version_info.minor,"python_abi":f"cp{sys.version_info.major}{sys.version_info.minor}",
            "os_family":"linux","architecture":"x86_64","libc_family":"glibc","libc_version":"2.17","macos_version":""},
        "base_interpreter_identity":{},"installation_root":str(tmp_path/"root"),"artifacts":arts}
    value["installation_plan_digest"]=semantic_digest(value); return value,paths

def test_exact_offline_argv_and_six_wheel_admission(tmp_path):
    value,paths=plan(tmp_path); argv=build_offline_pip_argv(Path("/usr/bin/python").resolve(),paths)
    assert argv[-6:]==list(map(str,paths))
    assert {"--no-index","--no-deps","--no-cache-dir","--no-compile"} <= set(argv)
    assert not ({"--upgrade-deps","--upgrade","-e","-r","-c","--find-links"} & set(argv))
    with pytest.raises(InstallationError): build_offline_pip_argv(Path("/usr/bin/python").resolve(),paths+[paths[0]])
    with pytest.raises(InstallationError): build_offline_pip_argv(Path("/usr/bin/python").resolve(),paths[:-1]+["https://example/x.whl"])

def test_plan_authorization_and_receipt_digests_are_deterministic(tmp_path):
    value,_=plan(tmp_path); validate_plan(value)
    assert authorization_for(value,operator_confirmed=True)==authorization_for(value,operator_confirmed=True)
    receipt={"installed_at":"one","runtime_available_for_import":False}
    assert receipt_semantic_digest(receipt)==receipt_semantic_digest({**receipt,"installed_at":"two"})
    broken=dict(value); broken["runtime_id"]="wrong"
    with pytest.raises(InstallationError): validate_plan(broken)

def test_dry_run_creates_nothing_and_missing_authorization_blocks(tmp_path):
    value,paths=plan(tmp_path); observed=value["environment"]
    result=install(value,wheel_paths=paths,observed_environment=observed)
    assert result["status"]=="inspection_ready" and not Path(value["installation_root"]).exists()
    with pytest.raises(InstallationError,match="installation_authorization_invalid"):
        install(value,wheel_paths=paths,observed_environment=observed,execute=True)
