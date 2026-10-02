from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

import sentientos.production_chat_resource_provisioning_actuator as actuator
from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceLedger
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from tests.test_production_chat_resource_provisioning_bundle_producer import NOW, inputs

pytestmark = pytest.mark.no_legacy_skip


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode()


def packet(tmp_path: Path, *, provisioning_id: str = "operator") -> tuple[bytes, object, dict[str, object]]:
    handle, values = inputs(tmp_path)
    def embedded(raw: bytes) -> dict[str, str]:
        return {"encoding": "base64url", "sha256": hashlib.sha256(raw).hexdigest(),
                "data": base64.urlsafe_b64encode(raw).rstrip(b"=").decode()}
    body: dict[str, object] = {
        "schema_version": actuator.REQUEST_SCHEMA,
        "installation_identity": handle.identity.value,
        "resource_provisioning_id": provisioning_id,
        "principal_artifact": embedded(values["principal_artifact"]),
        "provenance_artifact": embedded(values["provenance_artifact"]),
        "trusted_issuer_catalog_artifact": embedded(values["trusted_issuer_catalog_artifact"]),
        "principal_revocation_registry_artifact": embedded(values["principal_revocation_registry_artifact"]),
        "resource_policy_artifact": embedded(values["resource_policy_artifact"]),
        "requested_bounds": values["requested_bounds"].to_dict(),
        "requested_not_before": values["requested_not_before"],
        "requested_not_after": values["requested_not_after"],
    }
    raw = canonical({**body, "request_digest": hashlib.sha256(canonical(body)).hexdigest()})
    return raw, handle, values


def test_prepare_is_inert_and_exact_confirmation_creates_consumer_bundle(tmp_path: Path) -> None:
    raw, handle, _ = packet(tmp_path)
    before = sorted(path.relative_to(handle.root) for path in handle.root.rglob("*"))
    intent = actuator.prepare_provisioning_intent(raw)
    assert sorted(path.relative_to(handle.root) for path in handle.root.rglob("*")) == before
    result = actuator.execute_provisioning_intent(
        raw, confirmed_intent_digest=intent.intent_digest,
        registry=handle._registry, clock=lambda: NOW)
    owner = load_production_chat_resource_context_owner(
        handle, "operator", clock=lambda: NOW, nonce_source=lambda: "nonce")
    assert owner.allocator.ledger.snapshot_counts() == (1, 0, 0)
    assert owner.allocator.ledger.remaining_calls(result.allocation_id) == 2
    owner.allocator.final_gate(
        allocation=owner.allocation, principal=owner.principal,
        authenticated=owner.authenticated, current=owner.current, policy=owner.policy,
        current_time=NOW, durable_attempt_nonce="first")
    restarted = load_production_chat_resource_context_owner(
        handle, "operator", clock=lambda: NOW, nonce_source=lambda: "next")
    assert restarted.allocation.allocation_id == result.allocation_id
    assert restarted.allocator.ledger.remaining_calls(result.allocation_id) == 1


def test_execute_passes_exact_bytes_once_and_confirmation_precedes_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw, handle, values = packet(tmp_path)
    intent = actuator.prepare_provisioning_intent(raw)
    calls: list[dict[str, object]] = []
    original = actuator.produce_production_chat_resource_provisioning_bundle
    def observed(*args: object, **kwargs: object):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(actuator, "produce_production_chat_resource_provisioning_bundle", observed)
    with pytest.raises(actuator.ProductionChatResourceProvisioningActuatorError,
                       match="intent_confirmation_mismatch"):
        actuator.execute_provisioning_intent(raw, confirmed_intent_digest="0" * 64,
                                             registry=handle._registry, clock=lambda: NOW)
    assert calls == []
    actuator.execute_provisioning_intent(raw, confirmed_intent_digest=intent.intent_digest,
                                         registry=handle._registry, clock=lambda: NOW)
    assert len(calls) == 1
    for name in ("principal_artifact", "provenance_artifact", "trusted_issuer_catalog_artifact",
                 "principal_revocation_registry_artifact", "resource_policy_artifact"):
        assert calls[0][name] == values[name]


def test_mutations_invalidate_confirmation_and_same_id_stays_burned(tmp_path: Path) -> None:
    raw, handle, _ = packet(tmp_path)
    intent = actuator.prepare_provisioning_intent(raw)
    value = json.loads(raw)
    value["requested_bounds"]["max_input_chars"] += 1
    body = {key: item for key, item in value.items() if key != "request_digest"}
    changed = canonical({**body, "request_digest": hashlib.sha256(canonical(body)).hexdigest()})
    with pytest.raises(actuator.ProductionChatResourceProvisioningActuatorError,
                       match="intent_confirmation_mismatch"):
        actuator.execute_provisioning_intent(changed, confirmed_intent_digest=intent.intent_digest,
                                             registry=handle._registry, clock=lambda: NOW)
    actuator.execute_provisioning_intent(raw, confirmed_intent_digest=intent.intent_digest,
                                         registry=handle._registry, clock=lambda: NOW)
    with pytest.raises(Exception, match="provisioning_destination_not_unused"):
        actuator.execute_provisioning_intent(raw, confirmed_intent_digest=intent.intent_digest,
                                             registry=handle._registry, clock=lambda: NOW)
    ledger = GovernedLocalModelResourceLedger(
        handle.fixed_object("local-model/resource-provisioning/operator/resource-ledger.json").path)
    assert ledger.snapshot_counts() == (1, 0, 0)


@pytest.mark.parametrize("mutation,code", [
    (lambda value: value.update(extra=True), "request_fields_not_exact"),
    (lambda value: value.update(schema_version="wrong"), "unsupported_request_schema"),
    (lambda value: value.update(request_digest="x"), "invalid_request_digest"),
    (lambda value: value["principal_artifact"].update(encoding="base64"), "invalid_embedded_artifact"),
    (lambda value: value["principal_artifact"].update(data=value["principal_artifact"]["data"] + "="), "noncanonical_base64url"),
])
def test_closed_request_rejections(tmp_path: Path, mutation, code: str) -> None:
    raw, _, _ = packet(tmp_path)
    value = json.loads(raw); mutation(value)
    if code not in {"invalid_request_digest"}:
        body = {key: item for key, item in value.items() if key != "request_digest"}
        value["request_digest"] = hashlib.sha256(canonical(body)).hexdigest()
    with pytest.raises(actuator.ProductionChatResourceProvisioningActuatorError, match=code):
        actuator.load_provisioning_request(canonical(value))


def test_duplicate_key_and_nonfinite_are_rejected(tmp_path: Path) -> None:
    raw, _, _ = packet(tmp_path)
    duplicate = raw[:-1] + b',"schema_version":"x"}'
    with pytest.raises(actuator.ProductionChatResourceProvisioningActuatorError, match="duplicate_request_key"):
        actuator.load_provisioning_request(duplicate)
    with pytest.raises(actuator.ProductionChatResourceProvisioningActuatorError, match="invalid_request_json"):
        actuator.load_provisioning_request(raw.replace(b'"timeout_seconds":5.0', b'"timeout_seconds":NaN'))
