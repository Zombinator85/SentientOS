# mypy: ignore-errors
from __future__ import annotations

import time
from pathlib import Path
from runpy import run_path

import pytest

from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker,
    LocalModelInvocationBudget,
)
from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceLedger

pytestmark = pytest.mark.no_legacy_skip
BUDGET = LocalModelInvocationBudget(100, 200, 20, 5.0, 2)
TEST_ROOT = Path(__file__).parent
resource_setup = run_path(str(TEST_ROOT / "test_governed_local_model_resource_invocation_composition.py"))["setup"]
serving_setup = run_path(str(TEST_ROOT / "test_local_model_serving_inference.py"))["setup"]


def serving_at(monkeypatch, path, **kwargs):
    path.mkdir(parents=True, exist_ok=True)
    return serving_setup(monkeypatch, path, **kwargs)


def context_for(tmp_path):
    return resource_setup(tmp_path / "resource")[3:5]


def receipt_states(ledger):
    return [receipt["state"] for receipt in ledger._state["receipts"]]


def test_resource_backed_production_completion_forwards_exact_context_and_reconciles(
        monkeypatch, tmp_path):
    bridge, _, session, model, kernel, _ = serving_at(monkeypatch, tmp_path / "serving")
    context, ledger = context_for(tmp_path)
    seen = []
    original = GovernedLocalModelInvoker.invoke

    def observe(self, request, **kwargs):
        seen.append(kwargs.get("resource_context"))
        return original(self, request, **kwargs)

    monkeypatch.setattr(GovernedLocalModelInvoker, "invoke", observe)
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="resource-1",
                              budget=BUDGET, resource_context=context)
    assert seen == [context] and seen[0] is context
    assert receipt.status == "admitted_completed" and receipt.output_text == "answer"
    assert model.calls == 1 and ledger.remaining_calls(context.allocation.allocation_id) == 1
    assert GovernedLocalModelResourceLedger(ledger.path).remaining_calls(context.allocation.allocation_id) == 1
    assert receipt_states(ledger) == ["attempt_begun", "measured_completed", "reconciled"]
    assert ledger._state["receipts"][-1]["effect_receipt_digest"] == receipt.receipt_digest
    assert receipt.admission_decision_ref != session.binding["model_serving_admission_ref"]
    assert [request.authority_class for request in kernel.requests] == [
        AuthorityClass.MODEL_SERVING, AuthorityClass.LOCAL_MODEL_INFERENCE]


def test_resource_pre_effect_staleness_restores_without_generation(monkeypatch, tmp_path):
    bridge, serving, _, model, kernel, current = serving_at(monkeypatch, tmp_path / "serving")
    context, ledger = context_for(tmp_path)
    original = kernel.admit

    def stale_after_admission(request):
        decision = original(request)
        if request.authority_class is AuthorityClass.LOCAL_MODEL_INFERENCE:
            current[0] = {**current[0], "active_state": {**current[0]["active_state"], "generation": 2}}
        return decision

    kernel.admit = stale_after_admission
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="stale-before",
                              budget=BUDGET, resource_context=context)
    assert receipt.status == "backend_failure" and model.calls == 0
    assert ledger.remaining_calls(context.allocation.allocation_id) == 2
    assert receipt_states(ledger) == ["attempted_not_begun"] and serving.current_session() is None


def test_resource_post_effect_staleness_consumes_and_suppresses(monkeypatch, tmp_path):
    holder = {}

    def stale():
        evidence = holder["current"][0]
        holder["current"][0] = {**evidence, "active_state": {**evidence["active_state"], "generation": 2}}

    bridge, serving, _, model, _, current = serving_at(
        monkeypatch, tmp_path / "serving", on_generate=stale)
    holder["current"] = current
    context, ledger = context_for(tmp_path)
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="stale-after",
                              budget=BUDGET, resource_context=context)
    assert receipt.status == "serving_lifetime_stale_after_generation" and receipt.output_text is None
    assert model.calls == 1 and ledger.remaining_calls(context.allocation.allocation_id) == 1
    assert receipt_states(ledger) == ["attempt_begun", "measured_completed", "reconciled"]
    assert ledger._state["receipts"][-1]["effect_receipt_digest"] == receipt.receipt_digest
    assert serving.current_session() is None


def assert_post_entry_failure(monkeypatch, tmp_path, failure, expected_status, measured):
    bridge, _, _, model, _, _ = serving_at(
        monkeypatch, tmp_path / expected_status, on_generate=failure)
    context, ledger = context_for(tmp_path / expected_status)
    budget = LocalModelInvocationBudget(100, 200, 20, .001 if expected_status == "timeout" else 5, 2)
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id=expected_status,
                              budget=budget, resource_context=context)
    assert receipt.status == expected_status and model.calls == 1
    assert ledger.remaining_calls(context.allocation.allocation_id) == 1
    assert receipt_states(ledger) == ["attempt_begun", measured, "reconciled"]
    assert ledger._state["receipts"][-1]["effect_receipt_digest"] == receipt.receipt_digest


def test_resource_timeout_consumes_and_reconciles(monkeypatch, tmp_path):
    assert_post_entry_failure(
        monkeypatch, tmp_path, lambda: time.sleep(.02), "timeout", "measured_timeout")


def test_resource_backend_failure_consumes_and_reconciles(monkeypatch, tmp_path):
    def fail():
        raise RuntimeError("backend")

    assert_post_entry_failure(
        monkeypatch, tmp_path, fail, "backend_failure", "measured_backend_failure")


def test_denied_inference_and_serialized_caller_claims_never_debit(monkeypatch, tmp_path):
    bridge, serving, session, model, _, _ = serving_at(
        monkeypatch, tmp_path / "denied", inference=AdmissionOutcome.DENY)
    context, ledger = context_for(tmp_path / "denied")
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="denied",
                              budget=BUDGET, resource_context=context)
    assert receipt.status == "denied" and model.calls == 0 and not ledger._state["attempts"]
    assert serving.current_session() == session

    bridge, _, _, model, _, _ = serving_at(monkeypatch, tmp_path / "smuggled")
    _, untouched = context_for(tmp_path / "smuggled")
    claims = {name: "forged" for name in (
        "resource_context", "allocation_id", "allocation_digest", "principal_id",
        "principal_currentness", "durable_attempt_nonce", "call_entitlement")}
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="smuggled",
                              budget=BUDGET, caller_linkage=claims)
    assert receipt.status == "admitted_completed" and model.calls == 1
    assert receipt.request["linkage"]["caller_context"] == claims and not untouched._state["attempts"]


def test_duplicate_nonce_exhaustion_and_correlation_rollover_do_not_double_spend(monkeypatch, tmp_path):
    bridge, _, _, model, _, _ = serving_at(monkeypatch, tmp_path / "serving")
    context, ledger = context_for(tmp_path)
    first = bridge.generate(prompt="hello", caller="operator", correlation_id="first",
                            budget=BUDGET, resource_context=context)
    second = bridge.generate(prompt="hello", caller="operator", correlation_id="second",
                             budget=BUDGET, resource_context=context)
    assert first.status == "admitted_completed" and second.status == "resource_denied"
    assert "resource_gate:duplicate_attempt_id" in second.reason_codes
    assert model.calls == 1 and ledger.remaining_calls(context.allocation.allocation_id) == 1


def test_untrusted_context_shape_is_rejected_before_admission(monkeypatch, tmp_path):
    bridge, _, _, model, kernel, _ = serving_at(monkeypatch, tmp_path)
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="mapping",
                              budget=BUDGET, resource_context={"allocation_id": "forged"})
    assert receipt.status == "blocked_invalid" and model.calls == 0
    assert [request.authority_class for request in kernel.requests] == [AuthorityClass.MODEL_SERVING]


def test_resource_entitlement_does_not_contaminate_serving_or_model_identity(monkeypatch, tmp_path):
    bridge, _, session, _, _, _ = serving_at(monkeypatch, tmp_path)
    forbidden = {"allocation", "principal", "currentness", "resource_policy", "attempt_nonce"}
    assert forbidden.isdisjoint(session.binding)
    assert forbidden.isdisjoint(bridge.current_conversation_model_identity())
