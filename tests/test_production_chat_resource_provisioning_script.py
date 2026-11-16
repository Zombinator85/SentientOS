from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import scripts.production_chat_resource_provisioning as script
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget, validate_receipt,
)
from sentientos.host_resource_runtime import resource_consumption_world_state_records
from sentientos.installation_state import InstallationStateRegistry
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from sentientos.production_chat_resource_provisioning_actuator import (
    execute_provisioning_intent as real_execute, prepare_provisioning_intent,
)
from tests.test_production_chat_resource_provisioning_actuator import packet
from tests.test_production_chat_resource_provisioning_bundle_producer import NOW
from tests.test_production_chat_resource_provisioning_request_publisher import publish

pytestmark = pytest.mark.no_legacy_skip


def test_cli_has_only_prepare_create_and_one_request_path() -> None:
    parser = script.build_parser()
    subcommands = next(action for action in parser._actions if action.dest == "command").choices
    assert set(subcommands) == {"prepare", "create"}
    source = inspect.getsource(script)
    for forbidden in ("--principal", "--provenance", "--catalog", "--registry", "--policy",
                      "--source-root", "--state-root", "--destination", "--force",
                      "--create-installation", "--request-custody", "--receipt", "cleanup",
                      "renew", "retry"):
        assert forbidden not in source


def test_prepare_json_and_missing_or_wrong_confirmation_are_bounded(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw, _, _ = packet(tmp_path); path = tmp_path / "request.json"; path.write_bytes(raw)
    assert script.main(["prepare", "--request", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "production_resource_provisioning_intent_ready"
    assert output["intent"]["intent_digest"] == prepare_provisioning_intent(raw).intent_digest
    assert script.main(["create", "--request", str(path)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "production_resource_provisioning_blocked",
        "reason_code": "invalid_confirmation_digest",
    }
    assert script.main(["create", "--request", str(path),
                        "--confirm-intent-digest", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "intent_confirmation_mismatch"


def _select_registry(monkeypatch: pytest.MonkeyPatch, registry: InstallationStateRegistry) -> None:
    monkeypatch.setattr(InstallationStateRegistry, "system", classmethod(lambda cls: registry))


def test_fixed_custody_prepare_uses_consumer_and_is_inert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    handle, _, _ = publish(tmp_path)
    _select_registry(monkeypatch, handle._registry)
    exact = handle.read_regular(handle.fixed_object(
        "local-model/resource-provisioning-requests/request/request.json"))
    consumer_calls = 0
    original_consumer = script.load_published_production_chat_resource_provisioning_request

    def observed_consumer(*args: object) -> bytes:
        nonlocal consumer_calls
        consumer_calls += 1
        return original_consumer(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(script, "load_published_production_chat_resource_provisioning_request",
                        observed_consumer)
    monkeypatch.setattr(script, "execute_provisioning_intent",
                        lambda *args, **kwargs: pytest.fail("prepare executed"))
    before = sorted(path.relative_to(handle.root) for path in handle.root.rglob("*"))
    assert script.main(["prepare", "--installation-identity", "production",
                        "--resource-provisioning-id", "request"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "production_resource_provisioning_intent_ready"
    assert output["intent"] == prepare_provisioning_intent(exact).to_dict()
    assert consumer_calls == 1
    assert sorted(path.relative_to(handle.root) for path in handle.root.rglob("*")) == before
    assert not handle.fixed_object("local-model/resource-provisioning/request").path.exists()


@pytest.mark.parametrize("extra", [
    [], ["--installation-identity", "production"],
    ["--resource-provisioning-id", "request"],
    ["--request", "x", "--installation-identity", "production",
     "--resource-provisioning-id", "request"],
    ["--request", "x", "--installation-identity", "production"],
    ["--request", "x", "--resource-provisioning-id", "request"],
])
def test_source_mode_ambiguity_and_incompleteness_are_bounded(
    extra: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(script, "execute_provisioning_intent",
                        lambda *args, **kwargs: pytest.fail("invalid source executed"))
    assert script.main(["prepare", *extra]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "production_resource_provisioning_blocked",
        "reason_code": "invalid_request_source_mode",
    }


def test_fixed_custody_confirmation_failures_precede_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    handle, _, result = publish(tmp_path)
    _select_registry(monkeypatch, handle._registry)
    calls = 0
    original = script.execute_provisioning_intent

    def observed(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(script, "execute_provisioning_intent", observed)
    base = ["create", "--installation-identity", "production",
            "--resource-provisioning-id", "request"]
    assert script.main(base) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "invalid_confirmation_digest"
    assert script.main([*base, "--confirm-intent-digest", "bad"]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "invalid_confirmation_digest"
    assert script.main([*base, "--confirm-intent-digest", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "intent_confirmation_mismatch"
    assert calls == 0
    assert not handle.fixed_object("local-model/resource-provisioning/request").path.exists()
    assert result.intent_digest != "0" * 64


def test_confirmed_fixed_custody_create_uses_actuator_once_and_preserves_conservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    handle, _, published = publish(tmp_path)
    _select_registry(monkeypatch, handle._registry)
    calls = 0

    def execute(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real_execute(*args, **kwargs, clock=lambda: NOW)  # type: ignore[arg-type]

    monkeypatch.setattr(script, "execute_provisioning_intent", execute)
    command = ["create", "--installation-identity", "production",
               "--resource-provisioning-id", "request",
               "--confirm-intent-digest", published.intent_digest]
    assert script.main(command) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "production_resource_provisioning_created"
    assert calls == 1
    owner = load_production_chat_resource_context_owner(
        handle, "request", clock=lambda: NOW, nonce_source=lambda: "nonce")
    assert owner.allocator.ledger.snapshot_counts() == (1, 0, 0)
    assert owner.allocator.ledger.remaining_calls(output["allocation_id"]) == 2
    owner.close()
    reloaded = load_production_chat_resource_context_owner(
        handle, "request", clock=lambda: NOW, nonce_source=lambda: "restart")
    assert reloaded.allocator.ledger.snapshot_counts() == (1, 0, 0)
    reloaded.close()
    assert script.main(command) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "provisioning_destination_not_unused"


def test_published_request_to_confirmed_resource_backed_invocation_is_one_causal_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Join request custody, explicit creation, owner loading, inference, and ledger custody.

    The backend and model artifact are deterministic test fixtures. This proves the
    software custody path, not host hardware scheduling or observed resource pressure.
    """
    handle, _, published = publish(tmp_path)
    _select_registry(monkeypatch, handle._registry)

    def execute(*args: object, **kwargs: object) -> object:
        return real_execute(*args, **kwargs, clock=lambda: NOW)  # type: ignore[arg-type]
    monkeypatch.setattr(script, "execute_provisioning_intent", execute)
    command = ["create", "--installation-identity", "production",
        "--resource-provisioning-id", "request",
        "--confirm-intent-digest", published.intent_digest]
    assert script.main(command) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "production_resource_provisioning_created"

    owner = load_production_chat_resource_context_owner(
        handle, "request", clock=lambda: NOW, nonce_source=lambda: "runtime-attempt-1")
    artifact = tmp_path / "fixture-model.gguf"
    artifact.write_bytes(b"deterministic synthetic model artifact")
    model_config = ModelConfig(
        [ModelCandidate(artifact, "llama_cpp", "synthetic-resource-integration")],
        generation=GenerationConfig(max_new_tokens=8),
    )
    authority = build_local_model_authority_map(model_config, allowed_roots=[tmp_path])

    class SyntheticBackend:
        calls = 0

        def generate(self, _prompt: str, **_kwargs: object) -> str:
            self.calls += 1
            return "synthetic governed response"

    backend = SyntheticBackend()
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
        decisions_path=tmp_path / "invocation-decisions.jsonl")
    invoker = GovernedLocalModelInvoker(model=backend, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "invocation-runtime")
    request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="resource-provisioning-integration", correlation_id="one-provisioned-call",
        budget=LocalModelInvocationBudget(100, 200, 8, 5.0, 2))
    try:
        receipt = invoker.invoke(request, resource_context=owner.next_context())
        assert receipt.status == "admitted_completed"
        assert receipt.output_text == "synthetic governed response"
        assert backend.calls == 1
        valid, findings = validate_receipt(receipt.to_dict())
        assert valid, findings
        assert receipt.resource_allocation_digest == owner.allocation.allocation_digest
        assert owner.allocator.ledger.snapshot_counts() == (1, 1, 3)
        assert owner.allocator.ledger.remaining_calls(owner.allocation.allocation_id) == 1

        owner.close()
        recovered_owner = load_production_chat_resource_context_owner(
            handle, "request", clock=lambda: NOW, nonce_source=lambda: "restart-nonce")
        try:
            assert recovered_owner.allocation.allocation_id == owner.allocation.allocation_id
            assert recovered_owner.allocator.ledger.remaining_calls(
                owner.allocation.allocation_id) == 1
            projected = resource_consumption_world_state_records(
                ledger=recovered_owner.allocator.ledger,
                invocation_receipts=(receipt.to_dict(),))[0]
            assert projected["disposition"] == "recorded"
            assert projected["payload"]["invocation_receipts"][0][
                "resource_allocation_digest"] == owner.allocation.allocation_digest
            assert not projected["payload"]["lineage_findings"]
        finally:
            recovered_owner.close()
    finally:
        owner.close()
