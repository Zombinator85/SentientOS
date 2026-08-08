from __future__ import annotations
import json
from pathlib import Path
import pytest
from sentientos import maintenance_windows_live_bootstrap as bootstrap

pytestmark=pytest.mark.no_legacy_skip

def manifest(tmp_path:Path)->dict[str,object]:
 repo=tmp_path/"repo";repo.mkdir();(repo/".git").mkdir(); fixture=repo/"tests"/"fixtures";fixture.mkdir(parents=True)
 value=bootstrap.template();value.update(repository_root=str(repo),expected_repository_sha="a"*40,external_custody_root=str(tmp_path/"custody"),canary_source_path=str(fixture/"canary.txt"),canary_allowed_path_boundary=str(fixture),allowed_path_prefixes=["tests/fixtures/canary.txt"],authority_classes=["filesystem_read"],validation_expectations=["tests/test_x.py::test_x"],activation_not_before="2030-01-01T00:00:00Z",activation_expires_at="2030-01-02T00:00:00Z",evaluation_time="2030-01-01T12:00:00Z")
 return value

def test_closed_manifest_binds_canary_and_rejects_secrets(tmp_path:Path)->None:
 value=manifest(tmp_path);assert bootstrap.validate_manifest(value)["expected_repository_sha"]=="a"*40
 bad=dict(value);bad["api_key"]="x"
 with pytest.raises(ValueError,match="closed_bootstrap"):bootstrap.validate_manifest(bad)
 bad=dict(value);bad["external_custody_root"]=str(Path(value["repository_root"])/"custody")
 with pytest.raises(ValueError,match="inside_repository"):bootstrap.validate_manifest(bad)

def test_template_uses_real_windows_example_and_explicit_policy()->None:
 value=bootstrap.template();assert value["repository_root"]==r"C:\SentientOS";assert "authority_classes" in value and "budgets" in value

def test_inspect_host_delegates_to_existing_capability(monkeypatch:pytest.MonkeyPatch,tmp_path:Path)->None:
 seen=[];monkeypatch.setattr(bootstrap.readiness,"inspect_host",lambda root:(seen.append(root) or {"status":"windows_host_inspected"}))
 assert bootstrap.inspect_host(tmp_path)["status"]=="windows_host_inspected" and seen==[tmp_path]

def test_conflicting_output_and_digest_tampering_block(tmp_path:Path)->None:
 path=tmp_path/"a.json";bootstrap._write(path,{"a":1})
 with pytest.raises(ValueError,match="conflicting"):bootstrap._write(path,{"a":2})
 index={"schema_version":bootstrap.INDEX_SCHEMA,"index_digest":"bad","artifacts":{}}
 ip=tmp_path/"index.json";ip.write_bytes(bootstrap.canonical_bytes(index))
 assert bootstrap.verify(ip,evaluation_time="2030-01-01T00:00:00Z")["status"]==bootstrap.STATUS_BLOCKED

def test_printed_machine_json_is_canonical(tmp_path:Path,capsys:pytest.CaptureFixture[str])->None:
 from scripts.maintenance_windows_live_bootstrap import main
 out=tmp_path/"template.json";assert main(["write-template","--output",str(out)])==0
 payload=capsys.readouterr().out;assert payload==bootstrap.canonical_bytes(json.loads(payload)).decode()
