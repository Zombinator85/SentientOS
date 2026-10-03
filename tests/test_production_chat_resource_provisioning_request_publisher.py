from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

import sentientos.production_chat_resource_provisioning_request_publisher as publisher
from sentientos.installation_state import InstallationStateHandle
from sentientos.production_chat_resource_provisioning_actuator import load_provisioning_request, prepare_provisioning_intent
from tests.test_production_chat_resource_provisioning_bundle_producer import NOW, inputs

pytestmark = pytest.mark.no_legacy_skip


def publish(tmp_path: Path, provisioning_id: str = "request", **changes: object) -> tuple[Any, dict[str, Any], Any]:
    handle, values = inputs(tmp_path)
    clock = values.pop("clock")
    values = {**values, "publication_clock": clock, **changes}
    return handle, values, publisher.publish_production_chat_resource_provisioning_request(
        handle, provisioning_id, **values)


def test_successful_receipt_last_publication_and_digest_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    original = InstallationStateHandle.durable_create
    def observed(self: Any, obj: Any, data: bytes, **options: object) -> None:
        order.append(obj.relative.parts[-1])
        original(self, obj, data, **options)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", observed)
    handle, values, result = publish(tmp_path)
    assert order == ["request.json", "publication-receipt.json"]
    prefix = "local-model/resource-provisioning-requests/request/"
    request_bytes = handle.read_regular(handle.fixed_object(prefix + "request.json"))
    receipt_bytes = handle.read_regular(handle.fixed_object(prefix + "publication-receipt.json"))
    receipt = json.loads(receipt_bytes)
    assert len(receipt) == 21
    body = dict(receipt); digest = body.pop("receipt_digest")
    assert digest == hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    assert receipt["authority_definition_digest"] == publisher.AUTHORITY_DEFINITION_DIGEST
    assert receipt["verified_at"] == NOW
    assert result.receipt_digest == digest
    assert not handle.fixed_object("local-model/resource-provisioning/request").path.exists()


def test_exact_bytes_actuator_round_trip_and_deterministic_intent(tmp_path: Path) -> None:
    handle, values, result = publish(tmp_path)
    raw = handle.read_regular(handle.fixed_object(
        "local-model/resource-provisioning-requests/request/request.json"))
    loaded = load_provisioning_request(raw)
    for name in ("principal_artifact", "provenance_artifact", "trusted_issuer_catalog_artifact",
                 "principal_revocation_registry_artifact", "resource_policy_artifact"):
        assert getattr(loaded, name) == values[name]
    encoded = json.loads(raw)
    assert all("=" not in encoded[name]["data"] for name in (
        "principal_artifact", "provenance_artifact", "trusted_issuer_catalog_artifact",
        "principal_revocation_registry_artifact", "resource_policy_artifact"))
    body = dict(encoded); claimed = body.pop("request_digest")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                           allow_nan=False).encode()
    assert claimed == hashlib.sha256(canonical).hexdigest() == result.request_digest
    assert prepare_provisioning_intent(raw).intent_digest == result.intent_digest


def test_preflight_failure_has_no_request_custody_and_clock_called_once(tmp_path: Path) -> None:
    handle, values = inputs(tmp_path); calls = 0
    def clock() -> str:
        nonlocal calls; calls += 1
        return "2026-09-21T09:15:00Z"
    values.pop("clock")
    with pytest.raises(publisher.ProductionChatResourceProvisioningRequestPublisherError,
                       match="resource_policy_not_current"):
        publisher.publish_production_chat_resource_provisioning_request(
            handle, "stale", publication_clock=clock, **values)
    assert calls == 1
    assert not handle.fixed_object("local-model/resource-provisioning-requests/stale").path.exists()


def test_same_id_is_burned_without_second_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle, values = inputs(tmp_path); clock = values.pop("clock")
    publisher.publish_production_chat_resource_provisioning_request(
        handle, "once", publication_clock=clock, **values)
    calls = 0; original = InstallationStateHandle.durable_create
    def counted(self: Any, obj: Any, data: bytes, **options: object) -> None:
        nonlocal calls; calls += 1
        original(self, obj, data, **options)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", counted)
    with pytest.raises(publisher.ProductionChatResourceProvisioningRequestPublisherError,
                       match="request_destination_not_unused"):
        publisher.publish_production_chat_resource_provisioning_request(
            handle, "once", publication_clock=clock, **values)
    assert calls == 0


def test_partial_failure_leaves_request_and_burns_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle, values = inputs(tmp_path); clock = values.pop("clock")
    original = InstallationStateHandle.durable_create
    def fail_receipt(self: Any, obj: Any, data: bytes, **options: object) -> None:
        if obj.relative.parts[-1] == "publication-receipt.json":
            raise OSError("injected")
        original(self, obj, data, **options)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", fail_receipt)
    with pytest.raises(publisher.ProductionChatResourceProvisioningRequestPublisherError,
                       match="request_publication_failed"):
        publisher.publish_production_chat_resource_provisioning_request(
            handle, "partial", publication_clock=clock, **values)
    directory = handle.fixed_object("local-model/resource-provisioning-requests/partial")
    assert handle.list_regular_names(directory) == ("request.json",)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", original)
    with pytest.raises(publisher.ProductionChatResourceProvisioningRequestPublisherError,
                       match="request_destination_not_unused"):
        publisher.publish_production_chat_resource_provisioning_request(
            handle, "partial", publication_clock=clock, **values)
    assert handle.list_regular_names(directory) == ("request.json",)


def test_concurrent_same_id_exclusion(tmp_path: Path) -> None:
    handle, values = inputs(tmp_path); clock = values.pop("clock")
    def run() -> object:
        try:
            return publisher.publish_production_chat_resource_provisioning_request(
                handle, "race", publication_clock=clock, **values)
        except publisher.ProductionChatResourceProvisioningRequestPublisherError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sum(not isinstance(value, str) for value in results) == 1
    assert handle.list_regular_names(handle.fixed_object(
        "local-model/resource-provisioning-requests/race")) == (
            "publication-receipt.json", "request.json")


def test_invalid_bounds_and_validity_fail_before_mutation(tmp_path: Path) -> None:
    handle, values = inputs(tmp_path); clock = values.pop("clock")
    too_large = type(values["requested_bounds"])(101, 200, 20, 5.0, 2)
    with pytest.raises(publisher.ProductionChatResourceProvisioningRequestPublisherError,
                       match="requested_bounds_exceed_policy"):
        publisher.publish_production_chat_resource_provisioning_request(
            handle, "wide", publication_clock=clock, **{**values, "requested_bounds": too_large})
    with pytest.raises(publisher.ProductionChatResourceProvisioningRequestPublisherError,
                       match="invalid_requested_validity"):
        publisher.publish_production_chat_resource_provisioning_request(
            handle, "interval", publication_clock=clock,
            **{**values, "requested_not_after": values["requested_not_before"]})
    assert not handle.fixed_object("local-model/resource-provisioning-requests").path.exists()


def test_no_forbidden_runtime_surfaces_or_path_authority() -> None:
    parameters = inspect.signature(
        publisher.publish_production_chat_resource_provisioning_request).parameters
    assert not {"source_path", "destination_path", "state_root", "registry"}.intersection(parameters)
    source = inspect.getsource(publisher)
    for forbidden in ("execute_provisioning_intent", "produce_production_chat_resource_provisioning_bundle",
                      "RootPrincipalIssuer(", "PrivateKeyCustody", "ProvenanceSigner(",
                      ".mint_root", ".issue(", "model.generate", "durable_replace", "startup"):
        assert forbidden not in source
