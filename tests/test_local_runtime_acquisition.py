from __future__ import annotations
import hashlib
import io
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.local_runtime_acquisition import (
    AcquisitionError, StreamResponse, acquire_runtime_artifact, authorization_for,
    receipt_semantic_digest, validate_binding,
)
from sentientos.local_runtime_provisioning import semantic_digest, validate_runtime_catalog


def fixture(tmp_path: Path, data: bytes = b"bounded-runtime-wheel"):
    digest = hashlib.sha256(data).hexdigest()
    entry = {"runtime_id":"synthetic-cpu", "engine":"llama_cpp", "backend_family":"cpu", "backend_variant":"cpu",
             "distribution_kind":"python_wheel", "package_name":"llama-cpp-python", "package_version":"0.3.35",
             "artifact_filename":"llama_cpp_python-0.3.35-py3-none-win_amd64.whl", "artifact_sha256":digest,
             "artifact_size_bytes":len(data), "artifact_urls":["https://github.com/example/releases/download/v1/artifact.whl"],
             "runtime_priority":1, "python_implementation":"cpython", "python_tag":"py3", "abi_tag":"none",
             "platform_tag":"win_amd64", "supported_python_versions":["3.11"], "external_prerequisite_codes":[]}
    raw = {"schema_version":"sentientos.local_runtime_catalog:v2", "runtimes":[entry]}
    path = tmp_path / "catalog.json"; path.write_text(json.dumps(raw), encoding="utf-8")
    normalized = validate_runtime_catalog(raw); normalized_entry = normalized["runtimes"][0]
    plan = {"schema_version":"sentientos.local_runtime_provisioning:v1", "status":"selected",
            "runtime_catalog_digest":normalized["catalog_digest"], **{k: normalized_entry[k] for k in
            ("runtime_id","engine","backend_family","backend_variant","package_name","package_version","artifact_filename",
             "artifact_sha256","artifact_size_bytes","artifact_urls")}}
    plan["provisioning_plan_digest"] = semantic_digest(plan)
    return data, path, plan


class FakeTransport:
    def __init__(self, data: bytes, *, length=True, hosts=("github.com",), redirects=0, error=None):
        self.data, self.length, self.hosts, self.redirects, self.error, self.calls = data, length, hosts, redirects, error, 0
    def __call__(self, url: str) -> StreamResponse:
        self.calls += 1
        if self.error: raise self.error
        headers = {"Content-Length":str(len(self.data))} if self.length else {}
        return StreamResponse(io.BytesIO(self.data), headers, self.hosts, self.redirects)


def execute(tmp_path: Path, data: bytes, catalog: Path, plan: dict, transport=None):
    root = tmp_path / "escrow"; auth = authorization_for(plan, root, operator_confirmed=True)
    return acquire_runtime_artifact(plan, catalog_path=catalog, escrow_root=root, authorization=auth, execute=True,
                                    transport=transport or FakeTransport(data),
                                    disk_usage_provider=lambda _: SimpleNamespace(free=10**9))


def test_selected_plan_validates_and_dry_run_is_zero_effect(tmp_path: Path) -> None:
    _, catalog, plan = fixture(tmp_path); root = tmp_path / "absent"
    validate_binding(plan, catalog)
    result = acquire_runtime_artifact(plan, catalog_path=catalog, escrow_root=root)
    assert result["status"] == "inspection_ready" and not root.exists()


@pytest.mark.parametrize(("change","code"), [(lambda p:p.update(status="blocked"), "provisioning_plan_not_selected"),
    (lambda p:p.update(runtime_id="wrong"), "invalid_provisioning_plan"),
    (lambda p:p.update(runtime_catalog_digest="0"*64), "invalid_provisioning_plan"),
    (lambda p:p.update(artifact_sha256="0"*64), "invalid_provisioning_plan"),
    (lambda p:p.update(artifact_size_bytes=99), "invalid_provisioning_plan"),
    (lambda p:p.update(artifact_filename="../x.whl"), "invalid_provisioning_plan")])
def test_invalid_or_unbound_plan_rejected_before_network(tmp_path: Path, change, code: str) -> None:
    _, catalog, plan = fixture(tmp_path); change(plan); transport = FakeTransport(b"")
    with pytest.raises(AcquisitionError, match=code):
        acquire_runtime_artifact(plan, catalog_path=catalog, escrow_root=tmp_path/"e", execute=True, transport=transport)
    assert transport.calls == 0


def test_absent_or_wrong_authorization_rejected(tmp_path: Path) -> None:
    data, catalog, plan = fixture(tmp_path)
    with pytest.raises(AcquisitionError, match="invalid_acquisition_authorization"):
        acquire_runtime_artifact(plan, catalog_path=catalog, escrow_root=tmp_path/"e", execute=True, transport=FakeTransport(data))


def test_insufficient_space_blocks_before_network(tmp_path: Path) -> None:
    data, catalog, plan = fixture(tmp_path); transport = FakeTransport(data); root=tmp_path/"e"
    with pytest.raises(AcquisitionError, match="insufficient_escrow_space"):
        acquire_runtime_artifact(plan, catalog_path=catalog, escrow_root=root, execute=True,
            authorization=authorization_for(plan, root, operator_confirmed=True), transport=transport,
            disk_usage_provider=lambda _:SimpleNamespace(free=0))
    assert transport.calls == 0


def test_end_to_end_streamed_bytes_publish_verified_receipt_and_cache_hit(tmp_path: Path) -> None:
    data, catalog, plan = fixture(tmp_path); transport=FakeTransport(data, length=False, hosts=("github.com","release-assets.githubusercontent.com"), redirects=1)
    first = execute(tmp_path, data, catalog, plan, transport)
    final = tmp_path/"escrow"/"sha256"/hashlib.sha256(data).hexdigest()
    assert first["status"] == "acquired_verified" and (final/plan["artifact_filename"]).read_bytes() == data
    assert first["package_install_performed"] is first["runtime_import_performed"] is first["model_load_performed"] is first["commissioning_performed"] is False
    second_transport=FakeTransport(b"wrong")
    second = execute(tmp_path, data, catalog, plan, second_transport)
    assert second["status"] == "already_present_verified" and not second["network_performed"] and second_transport.calls == 0


@pytest.mark.parametrize(("payload","length","code"), [(b"short", True, "artifact_size_mismatch"),
    (b"bounded-runtime-wheem", False, "artifact_hash_mismatch"), (b"bounded-runtime-wheel-extra", False, "artifact_size_mismatch")])
def test_size_or_hash_mismatch_never_publishes(tmp_path: Path, payload: bytes, length: bool, code: str) -> None:
    data, catalog, plan = fixture(tmp_path)
    with pytest.raises(AcquisitionError, match=code): execute(tmp_path, data, catalog, plan, FakeTransport(payload, length=length))
    assert not (tmp_path/"escrow"/"sha256"/plan["artifact_sha256"]).exists()


def test_transport_failure_never_publishes(tmp_path: Path) -> None:
    data,catalog,plan=fixture(tmp_path)
    with pytest.raises(RuntimeError, match="network"): execute(tmp_path,data,catalog,plan,FakeTransport(data,error=RuntimeError("network")))
    assert not (tmp_path/"escrow"/"sha256"/plan["artifact_sha256"]).exists()


def test_corrupt_existing_and_symlinked_root_fail_closed(tmp_path: Path) -> None:
    data,catalog,plan=fixture(tmp_path); root=tmp_path/"escrow"; final=root/"sha256"/plan["artifact_sha256"]
    final.mkdir(parents=True); (final/"junk").write_text("x")
    with pytest.raises(AcquisitionError, match="existing_escrow_conflict"): execute(tmp_path,data,catalog,plan)
    shutil.rmtree(root); target=tmp_path/"target"; target.mkdir(); root.symlink_to(target, target_is_directory=True)
    with pytest.raises(AcquisitionError, match="unsafe_escrow_path"): execute(tmp_path,data,catalog,plan)


def test_concurrent_publication_converges(tmp_path: Path) -> None:
    data,catalog,plan=fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:execute(tmp_path,data,catalog,plan), range(2)))
    assert sorted(r["status"] for r in results) == ["acquired_verified", "already_present_verified"]


def test_receipt_semantic_digest_is_order_and_timestamp_stable() -> None:
    one={"b":2,"a":1,"retrieved_at":"now"}; two={"a":1,"retrieved_at":"later","b":2}
    assert receipt_semantic_digest(one) == receipt_semantic_digest(two)
