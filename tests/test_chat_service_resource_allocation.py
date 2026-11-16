# mypy: ignore-errors
from __future__ import annotations

import pytest

import sentientos.chat_service as chat_service
from sentientos.gaming_companion_core_runtime import WSLCoreGamingCompanionRuntime
from sentientos.production_chat_resource_context import ProductionChatResourceContextOwner

pytestmark = pytest.mark.no_legacy_skip


def test_configure_production_chat_rejects_nonexact_owner_before_establishing(monkeypatch):
    with pytest.raises(TypeError, match="exact_production_chat_resource_context_owner_required"):
        chat_service.configure_production_chat(
            installation_identity="not-used", serving_operation_id="op",
            resource_context_owner=object())  # type: ignore[arg-type]


def test_configure_production_chat_requires_governed_resource_owner_before_custody(
        monkeypatch):
    monkeypatch.setattr(chat_service, "open_chat_process_handoff",
        lambda **_kwargs: pytest.fail("process custody opened before resource governance"))
    with pytest.raises(ValueError,
                       match="resource_provisioning_context_required_for_production_chat"):
        chat_service.configure_production_chat(
            installation_identity="Install-1", serving_operation_id="op",
            runtime_handoff_id="handoff-1")


def test_configure_production_chat_validates_resource_identity_before_custody(
        monkeypatch):
    monkeypatch.setattr(chat_service, "open_chat_process_handoff",
        lambda **_kwargs: pytest.fail("process custody opened for invalid resource identity"))
    with pytest.raises(ValueError, match="invalid_resource_provisioning_id"):
        chat_service.configure_production_chat(
            installation_identity="Install-1", serving_operation_id="op",
            runtime_handoff_id="handoff-1", resource_provisioning_id="../bad")


def test_remote_avatar_output_requires_owned_core_session():
    with pytest.raises(TypeError, match="exact_wsl_core_avatar_output_session_required"):
        chat_service.configure_production_chat(
            installation_identity="not-used", serving_operation_id="op",
            avatar_output_session=object())

    runtime = WSLCoreGamingCompanionRuntime.__new__(WSLCoreGamingCompanionRuntime)
    runtime._state = "stopped"
    runtime._port = None
    runtime._bridge_runtime = type("BridgeStatus", (), {
        "status": lambda _self: type("Status", (), {
            "running": False, "accepted_messages": 0, "rejected_connections": 0})(),
    })()
    with pytest.raises(ValueError, match="wsl_core_gaming_companion_runtime_must_be_started"):
        chat_service.configure_production_chat(
            installation_identity="not-used", serving_operation_id="op",
            gaming_companion_runtime=runtime)


def test_chat_protocol_and_transaction_remain_resource_ignorant():
    annotations = chat_service.configure_production_chat.__annotations__
    assert "resource_context_owner" in annotations
    assert set(chat_service.ChatInference.generate.__annotations__) == {
        "prompt", "caller", "correlation_id", "budget", "caller_linkage", "return"
    }
    names = set(chat_service.PersistentConversationService.chat.__code__.co_names)
    assert not names.intersection({"allocation_id", "principal_id", "durable_attempt_nonce", "resource_context"})
    assert not set(chat_service.ChatResponse.__annotations__).intersection({
        "allocation_id", "principal_id", "durable_attempt_nonce", "attempt_id", "resource_policy"
    })
