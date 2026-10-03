from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable

import pytest

import sentientos.production_chat_resource_provisioning_request_consumer as consumer
from sentientos.installation_state import InstallationStateHandle
from sentientos.production_chat_resource_provisioning_actuator import (
    load_provisioning_request,
    prepare_provisioning_intent,
)
from sentientos.production_chat_resource_provisioning_request_publisher import (
    publish_production_chat_resource_provisioning_request,
)
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs

pytestmark = pytest.mark.no_legacy_skip


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode()


def published(tmp_path: Path, provisioning_id: str = "consumer") -> tuple[Any, dict[str, Any], bytes, bytes]:
    handle, values = inputs(tmp_path)
    clock = values.pop("clock")
    publish_production_chat_resource_provisioning_request(
        handle, provisioning_id, publication_clock=clock, **values)
    prefix = f"local-model/resource-provisioning-requests/{provisioning_id}/"
    request = handle.read_regular(handle.fixed_object(prefix + "request.json"))
    receipt = handle.read_regular(handle.fixed_object(prefix + "publication-receipt.json"))
    return handle, values, request, receipt


def replace_receipt(handle: Any, provisioning_id: str, mutate: Callable[[dict[str, Any]], None],
                    *, digest: bool = True) -> None:
    path = handle.fixed_object(
        f"local-model/resource-provisioning-requests/{provisioning_id}/publication-receipt.json").path
    value = json.loads(path.read_bytes())
    mutate(value)
    if digest:
        body = dict(value); body.pop("receipt_digest", None)
        value["receipt_digest"] = hashlib.sha256(canonical(body)).hexdigest()
    path.write_bytes(canonical(value))


def load(handle: Any, provisioning_id: str = "consumer") -> bytes:
    return consumer.load_published_production_chat_resource_provisioning_request(
        handle, provisioning_id)


def test_real_publisher_exact_byte_round_trip_and_intent_binding(tmp_path: Path) -> None:
    handle, _, request, receipt = published(tmp_path)
    returned = load(handle)
    assert returned is not request
    assert returned == request
    assert load_provisioning_request(returned)._packet == request
    intent = prepare_provisioning_intent(returned)
    assert intent.request_digest == json.loads(receipt)["request_digest"]
    assert intent.intent_digest == json.loads(receipt)["intent_digest"]


def test_consumer_is_zero_mutation_and_zero_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle, _, request, _ = published(tmp_path)
    before = {str(path.relative_to(handle.root)): (path.stat().st_mode, path.read_bytes())
              for path in handle.root.rglob("*") if path.is_file()}
    for name in ("ensure_directory", "durable_create", "durable_replace", "exclusive_lock"):
        monkeypatch.setattr(InstallationStateHandle, name,
                            lambda *args, _name=name, **kwargs: pytest.fail(_name))
    assert load(handle) == request
    after = {str(path.relative_to(handle.root)): (path.stat().st_mode, path.read_bytes())
             for path in handle.root.rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.parametrize("missing", ["request.json", "publication-receipt.json"])
def test_missing_publication_objects_fail_closed(tmp_path: Path, missing: str) -> None:
    handle, _, _, _ = published(tmp_path)
    handle.fixed_object(f"local-model/resource-provisioning-requests/consumer/{missing}").path.unlink()
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError,
                       match="published_request_custody_unavailable"):
        load(handle)


def test_bare_request_after_publisher_failure_is_unpublished(tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    handle, values = inputs(tmp_path); clock = values.pop("clock")
    original = InstallationStateHandle.durable_create
    def fail_receipt(self: Any, obj: Any, data: bytes, **options: object) -> None:
        if obj.relative.parts[-1] == "publication-receipt.json":
            raise OSError("injected")
        original(self, obj, data, **options)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", fail_receipt)
    with pytest.raises(Exception, match="request_publication_failed"):
        publish_production_chat_resource_provisioning_request(
            handle, "partial", publication_clock=clock, **values)
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError,
                       match="published_request_custody_unavailable"):
        load(handle, "partial")


@pytest.mark.parametrize(("raw", "code"), [
    (b"{", "invalid_publication_receipt_json"),
    (b'{"schema_version":"a","schema_version":"b"}', "duplicate_custody_key"),
])
def test_malformed_or_duplicate_receipt_fails_closed(tmp_path: Path, raw: bytes, code: str) -> None:
    handle, _, _, _ = published(tmp_path)
    handle.fixed_object("local-model/resource-provisioning-requests/consumer/publication-receipt.json").path.write_bytes(raw)
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError, match=code):
        load(handle)


@pytest.mark.parametrize(("mutation", "digest", "code"), [
    (lambda r: r.update(extra=True), True, "receipt_fields_not_exact"),
    (lambda r: r.pop("principal_id"), True, "receipt_fields_not_exact"),
    (lambda r: r.update(schema_version="wrong"), True, "unsupported_receipt_schema"),
    (lambda r: r.update(receipt_digest="0" * 64), False, "receipt_digest_mismatch"),
    (lambda r: r.update(receipt_digest="BAD"), False, "invalid_receipt_digest"),
    (lambda r: r.update(request_digest="0" * 64), True, "request_digest_binding_mismatch"),
    (lambda r: r.update(intent_digest="0" * 64), True, "intent_digest_binding_mismatch"),
    (lambda r: r.update(installation_identity="other-installation"), True, "installation_identity_mismatch"),
    (lambda r: r.update(resource_provisioning_id="other"), True, "resource_provisioning_id_mismatch"),
    (lambda r: r.update(authority_definition_digest="0" * 64), True,
     "authority_definition_digest_mismatch"),
    (lambda r: r.update(verified_at="2026-09-21T09:15:00.000Z"), True, "invalid_verified_at"),
])
def test_receipt_structure_digest_and_identity_tampering_fails_closed(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None], digest: bool, code: str,
) -> None:
    handle, _, _, _ = published(tmp_path)
    replace_receipt(handle, "consumer", mutation, digest=digest)
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError, match=code):
        load(handle)


@pytest.mark.parametrize("field", [
    "principal_artifact_sha256", "provenance_artifact_sha256",
    "trusted_issuer_catalog_artifact_sha256", "principal_revocation_registry_artifact_sha256",
    "resource_policy_artifact_sha256",
])
def test_each_exact_artifact_byte_binding_is_enforced(tmp_path: Path, field: str) -> None:
    handle, _, _, _ = published(tmp_path)
    replace_receipt(handle, "consumer", lambda r: r.update({field: "0" * 64}))
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError,
                       match=field + "_binding_mismatch"):
        load(handle)


@pytest.mark.parametrize("field", [
    "principal_id", "principal_binding_digest", "provenance_digest",
    "trusted_issuer_catalog_version", "trusted_issuer_catalog_digest",
    "revocation_registry_version", "revocation_registry_digest", "resource_policy_digest",
])
def test_each_semantic_intent_binding_is_enforced(tmp_path: Path, field: str) -> None:
    handle, _, _, _ = published(tmp_path)
    replace_receipt(handle, "consumer", lambda r: r.update({field: "altered"}))
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError,
                       match=field + "_binding_mismatch"):
        load(handle)


def test_noncanonical_request_and_receipt_custody_fail_closed(tmp_path: Path) -> None:
    handle, _, request, receipt = published(tmp_path)
    request_path = handle.fixed_object(
        "local-model/resource-provisioning-requests/consumer/request.json").path
    request_path.write_bytes(b" " + request)
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError,
                       match="noncanonical_request_custody"):
        load(handle)
    request_path.write_bytes(request)
    receipt_path = handle.fixed_object(
        "local-model/resource-provisioning-requests/consumer/publication-receipt.json").path
    receipt_path.write_bytes(receipt + b"\n")
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError,
                       match="noncanonical_receipt_custody"):
        load(handle)


def test_duplicate_request_keys_remain_rejected_by_actuator_loader(tmp_path: Path) -> None:
    handle, _, request, _ = published(tmp_path)
    path = handle.fixed_object("local-model/resource-provisioning-requests/consumer/request.json").path
    path.write_bytes(request[:-1] + b',"schema_version":"wrong"}')
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError,
                       match="duplicate_custody_key"):
        load(handle)


@pytest.mark.parametrize("name", ["request.json", "publication-receipt.json"])
def test_nonregular_custody_objects_fail_closed(tmp_path: Path, name: str) -> None:
    handle, _, _, _ = published(tmp_path)
    path = handle.fixed_object(f"local-model/resource-provisioning-requests/consumer/{name}").path
    path.unlink(); path.mkdir()
    with pytest.raises(consumer.ProductionChatResourceProvisioningRequestConsumerError,
                       match="published_request_custody_unavailable"):
        load(handle)


def test_public_api_has_no_path_or_runtime_authority_surface() -> None:
    parameters = inspect.signature(
        consumer.load_published_production_chat_resource_provisioning_request).parameters
    assert list(parameters) == ["installation_handle", "resource_provisioning_id"]
    source = inspect.getsource(consumer)
    for forbidden in (
        "ensure_directory(", "durable_create(", "durable_replace(", ".unlink(", ".delete(",
        "publish_production_chat_resource_provisioning_request(", "execute_provisioning_intent(",
        "produce_production_chat_resource_provisioning_bundle(", "model.generate(", "mint_root(",
        "sign(", "startup(", "allocation_id",
    ):
        assert forbidden not in source
