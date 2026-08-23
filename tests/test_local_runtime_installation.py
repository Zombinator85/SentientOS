from pathlib import Path
import sys
import json
import base64
import csv
import hashlib
import io
import zipfile
import pytest
from sentientos.local_runtime_installation import (InstallationError, EXPECTED, authorization_for,
    base_interpreter_identity, build_offline_pip_argv, install, receipt_semantic_digest, validate_plan,
    verify_existing)
from sentientos.local_runtime_dependencies import semantic_digest

pytestmark = pytest.mark.no_legacy_skip

def _wheel(path: Path, name: str, version: str, marker: str = "") -> None:
    dist = name.replace("-", "_"); info = f"{dist}-{version}.dist-info"
    files = {f"{dist}/__init__.py": f"MARKER={marker!r}\n".encode(),
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\n".encode(),
        f"{info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: SentientOS-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    rows=[]
    for relative,data in files.items():
        digest=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        rows.append((relative,f"sha256={digest}",str(len(data))))
    rows.append((f"{info}/RECORD","","")); output=io.StringIO(); csv.writer(output,lineterminator="\n").writerows(rows)
    files[f"{info}/RECORD"]=output.getvalue().encode()
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_STORED) as archive:
        for relative,data in files.items(): archive.writestr(relative,data)

def plan(tmp_path: Path, *, valid_wheels: bool = False):
    arts=[]; paths=[]
    for i,(name,version) in enumerate(EXPECTED):
        p=(tmp_path/f"{name.replace('-','_')}-{version}-py3-none-any.whl").resolve(); p.write_bytes(bytes([i]))
        if valid_wheels: _wheel(p,name,version)
        arts.append({"artifact_id":name,"package":name,"version":version,"filename":p.name,
            "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"size":p.stat().st_size,
            "source_content_address":f"sha256:{hashlib.sha256(p.read_bytes()).hexdigest()}",
            "verified_source_path":str(p)}); paths.append(p)
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

def test_plan_bound_source_mismatches_block_before_mutation(tmp_path):
    for mutation in ("wrong_path", "reordered", "corrupt", "symlink"):
        case=tmp_path/mutation; case.mkdir(); value,paths=plan(case)
        value["base_interpreter_identity"]=base_interpreter_identity()
        value["installation_plan_digest"]=semantic_digest({k:v for k,v in value.items() if k!="installation_plan_digest"})
        if mutation=="wrong_path":
            other=case/"other.whl"; other.write_bytes(paths[0].read_bytes()); paths[0]=other
        elif mutation=="reordered": paths[0],paths[1]=paths[1],paths[0]
        elif mutation=="corrupt": paths[0].write_bytes(b"different")
        else:
            target=case/"target.whl"; paths[0].rename(target); paths[0].symlink_to(target)
        with pytest.raises(InstallationError,match="installation_source_artifact_mismatch"):
            install(value,wheel_paths=paths,observed_environment=value["environment"],
                authorization=authorization_for(value,operator_confirmed=True),execute=True)
        assert not Path(value["installation_root"]).exists()

def test_storage_preflight_blocks_before_mutation(tmp_path):
    value,paths=plan(tmp_path); value["base_interpreter_identity"]=base_interpreter_identity()
    value["installation_plan_digest"]=semantic_digest({k:v for k,v in value.items() if k!="installation_plan_digest"})
    usage=type("Usage",(),{"free":0})()
    with pytest.raises(InstallationError,match="installation_storage_preflight_failed"):
        install(value,wheel_paths=paths,observed_environment=value["environment"],
            authorization=authorization_for(value,operator_confirmed=True),execute=True,disk_usage=lambda _:usage)
    assert not Path(value["installation_root"]).exists()

def test_real_synthetic_six_wheel_install_and_existing_verification(tmp_path):
    value,paths=plan(tmp_path,valid_wheels=True); value["base_interpreter_identity"]=base_interpreter_identity()
    value["installation_plan_digest"]=semantic_digest({k:v for k,v in value.items() if k!="installation_plan_digest"})
    auth=authorization_for(value,operator_confirmed=True)
    receipt=install(value,wheel_paths=paths,observed_environment=value["environment"],authorization=auth,execute=True)
    assert receipt["status"]=="installed_verified" and receipt["runtime_installed"] is True
    for field in ("runtime_import_performed","runtime_available_for_import","model_load_performed",
            "commissioning_performed","runtime_execution_authority_granted"):
        assert receipt[field] is False
    final=Path(value["installation_root"])/value["installation_plan_digest"]
    assert not (final/"input-wheels").exists()
    again=install(value,wheel_paths=paths,observed_environment=value["environment"],authorization=auth,execute=True)
    assert again["status"]=="already_installed_verified"

def test_recomputed_tampered_receipt_is_rejected(tmp_path, monkeypatch):
    value,paths=plan(tmp_path); final=Path(value["installation_root"])/value["installation_plan_digest"]
    env=final/"environment"; env.mkdir(parents=True); (env/"pyvenv.cfg").write_text("include-system-site-packages = false\n")
    installed={"executable":"x","python_version":"3","soabi":"x","distributions":[],
        "bootstrap_distributions":[{"name":"pip","version":"1"}]}
    records={"status":"record_verified","verified_distributions":[],"count":0}
    from sentientos import local_runtime_installation as module
    expected=module._expected_receipt(value,authorization_for(value,operator_confirmed=True),installed,records)
    expected["runtime_id"]="tampered"; expected["receipt_semantic_digest"]=receipt_semantic_digest(expected)
    (final/"installation-receipt.json").write_text(json.dumps(expected))
    monkeypatch.setattr(module,"inspect_installed",lambda _:installed); monkeypatch.setattr(module,"verify_records",lambda *_:records)
    with pytest.raises(InstallationError,match="installation_target_conflict"): verify_existing(value,paths)

def test_pip_receives_only_private_staged_snapshots_and_failure_cleans_them(tmp_path, monkeypatch):
    value,paths=plan(tmp_path,valid_wheels=True); value["base_interpreter_identity"]=base_interpreter_identity()
    value["installation_plan_digest"]=semantic_digest({k:v for k,v in value.items() if k!="installation_plan_digest"})
    captured=[]
    from sentientos import local_runtime_installation as module
    real_run=module.subprocess.run
    def run(argv, **kwargs):
        if "pip" in argv and "install" in argv:
            captured.extend(argv); return type("Result",(),{"returncode":1})()
        return real_run(argv,**kwargs)
    monkeypatch.setattr(module.subprocess,"run",run)
    with pytest.raises(InstallationError,match="offline_pip_failed"):
        install(value,wheel_paths=paths,observed_environment=value["environment"],
            authorization=authorization_for(value,operator_confirmed=True),execute=True)
    wheel_args=[Path(arg) for arg in captured if str(arg).endswith(".whl")]
    assert len(wheel_args)==6 and all(p.parent.name=="input-wheels" for p in wheel_args)
    assert not set(map(str,paths)) & set(map(str,wheel_args))
    root=Path(value["installation_root"])
    assert not any(root.iterdir())
