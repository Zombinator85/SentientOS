# mypy: ignore-errors
from __future__ import annotations

import pytest

import sentientos.chat_service as chat_service
from sentientos.production_chat_resource_context import ProductionChatResourceContextOwner

pytestmark = pytest.mark.no_legacy_skip


def test_configure_production_chat_rejects_nonexact_owner_before_establishing(monkeypatch):
    with pytest.raises(TypeError, match="exact_production_chat_resource_context_owner_required"):
        chat_service.configure_production_chat(
            installation_identity="not-used", serving_operation_id="op",
            resource_context_owner=object())  # type: ignore[arg-type]


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
