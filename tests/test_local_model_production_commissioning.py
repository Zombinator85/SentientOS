from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.local_model import ActiveModelIdentity, ModelLoadError, candidate_configuration_digest
from sentientos.local_model_production_commissioning import (
    ProductionCommissioningError,
    activate,
    authorization_for,
    commission,
    compose_commissioning_plan,
    load_activation,
    revalidate_chain,
    route_load_configuration,
    verify_compatibility,
)
from sentientos.local_model_runtime_worker import ExactRuntimeLocalModel, MAX_PROTOCOL_BYTES, _environment
from sentientos.local_runtime_provisioning import semantic_digest


def _chain(model: Path, interpreter: Path, family: str = "cpu") -> dict[str, object]:
    data = model.read_bytes()
    return {
        "artifact_path": str(model), "artifact_sha256": hashlib.sha256(data).hexdigest(),
        "artifact_size_bytes": len(data), "interpreter_path": str(interpreter), "runtime_id": "rt",
        "backend_family": family, "model_id": "m", "artifact_id": "sha256:x", "route_id": family,
    }


def _compat(chain: dict[str, object]) -> dict[str, object]:
    value: dict[str, object] = {
        "status": "local_model_compatibility_verified", "chain_digest": semantic_digest(chain),
        "artifact_sha256": chain["artifact_sha256"], "artifact_size_bytes": chain["artifact_size_bytes"],
        "interpreter_path": chain["interpreter_path"], "runtime_id": chain["runtime_id"],
        "model_construction_performed": True, "semantic_generations": 0, "authority_granted": False,
    }
    value["receipt_semantic_digest"] = semantic_digest(value)
    return value


def _fake_model(config, outputs: list[str] | None = None):
    candidate = config.candidates[0]
    data = candidate.path.read_bytes()
    identity = ActiveModelIdentity(
        engine="llama_cpp", resolved_artifact_path=str(candidate.path.resolve()),
        semantic_artifact_identity="sha256:" + hashlib.sha256(data).hexdigest(),
        model_content_sha256=hashlib.sha256(data).hexdigest(), artifact_size_bytes=len(data),
        sidecar_metadata_digest=None,
        configuration_digest=candidate_configuration_digest(candidate, config, "llama_cpp"),
        candidate_index=0, posture="production", fallback=False,
    )
    calls: list[str] = []
    def generate(prompt: str, **kwargs: object) -> str:
        calls.append(prompt)
        return (outputs or ["ok"])[min(len(calls) - 1, len(outputs or ["ok"]) - 1)]
    return SimpleNamespace(config=config, active_identity=identity, generate=generate, calls=calls, close=lambda: None)


def test_route_configuration_is_explicit_and_ambient_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic")
    monkeypatch.setitem(__import__("sys").modules, "torch", object())
    assert route_load_configuration(_chain(model, Path("/python")))["n_gpu_layers"] == 0
    assert route_load_configuration(_chain(model, Path("/python"), "cuda"))["n_gpu_layers"] == 1


def test_compatibility_receipt_records_truthful_bounded_construction(tmp_path: Path) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic")
    observed: dict[str, object] = {}
    def runner(argv: list[str], **kwargs: object) -> CompletedProcess[str]:
        observed.update(argv=argv, kwargs=kwargs)
        payload = {"ok": True, "probe_mode": "bounded_model_construction_vocab_only", "semantic_generations": 0}
        return CompletedProcess([], 0, "SENTIENTOS_MODEL_COMPATIBILITY=" + json.dumps(payload), "")
    receipt = verify_compatibility(_chain(model, Path("/verified/python")), runner=runner)
    assert observed["argv"][0] == "/verified/python"  # type: ignore[index]
    assert "vocab_only=True" in observed["argv"][3]  # type: ignore[index]
    assert receipt["model_construction_performed"] is True and receipt["semantic_generations"] == 0
    assert receipt["commissioning_performed"] is receipt["authority_granted"] is False


@pytest.mark.parametrize("mode", ["malformed", "incompatible", "timeout", "stale"])
def test_compatibility_failures_are_explicit(tmp_path: Path, mode: str) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic"); chain = _chain(model, Path("/verified/python"))
    if mode == "stale": model.write_bytes(b"changed")
    def runner(*args: object, **kwargs: object) -> CompletedProcess[str]:
        if mode == "timeout": raise subprocess.TimeoutExpired("probe", 1)
        payload = "{" if mode == "malformed" else json.dumps({"ok": False, "semantic_generations": 0})
        return CompletedProcess([], 0, "SENTIENTOS_MODEL_COMPATIBILITY=" + payload, "")
    with pytest.raises(ProductionCommissioningError): verify_compatibility(chain, runner=runner)


def test_commissioning_authorization_mismatch_fails_before_model_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic"); chain = _chain(model, Path("/python"))
    monkeypatch.setattr("sentientos.local_model_production_commissioning.revalidate_chain", lambda value: dict(value))
    compatibility = _compat(chain); plan = compose_commissioning_plan(chain, compatibility, tmp_path / "out")
    loaded = False
    def factory(config):
        nonlocal loaded; loaded = True; return _fake_model(config)
    wrong = authorization_for(plan, operator_confirmed_plan_digest="wrong")
    with pytest.raises(ProductionCommissioningError, match="authorization"):
        commission(plan, compatibility, wrong, model_factory=factory)
    assert loaded is False
    assert plan == compose_commissioning_plan(chain, compatibility, tmp_path / "out")


def test_fabricated_self_consistent_commissioning_receipt_does_not_activate(tmp_path: Path) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic"); chain = _chain(model, Path("/verified/python"))
    receipt = {"schema_version": "sentientos.local_model_commissioning_receipt:v2", "status": "local_model_commissioned",
        "chain": chain, "load_configuration": route_load_configuration(chain), "authority_map": {}, "active_model_identity": {},
        "activated": False, "provider_network": False, "tool": False, "memory": False, "action": False,
        "adoption": False, "repository_mutation": False, "autonomous_invocation": False, "background_inference": False}
    receipt["receipt_semantic_digest"] = semantic_digest(receipt)
    with pytest.raises(ProductionCommissioningError, match="sealed_production_chain_required"):
        activate(receipt, tmp_path / "active.json")


@pytest.mark.parametrize("mutation", ["schema", "digest", "evidence"])
def test_sealed_production_chain_missing_or_malformed_fails_closed(tmp_path: Path, mutation: str) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic")
    chain = _chain(model, Path("/python")); chain.update(schema_version="sentientos.local_model_production_chain:v1",
        status="production_chain_reconstructed_current", authoritative_evidence={})
    chain["sealed_chain_digest"] = semantic_digest(chain)
    if mutation == "schema": chain["schema_version"] = "legacy"
    elif mutation == "digest": chain["sealed_chain_digest"] = "0" * 64
    else: chain.pop("authoritative_evidence")
    with pytest.raises(ProductionCommissioningError): revalidate_chain(chain)


def test_exact_runtime_worker_identity_environment_protocol_and_shutdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic"); interpreter = tmp_path / "python"; interpreter.write_text("x")
    chain = _chain(model, interpreter)
    writes: list[str] = []
    class Pipe:
        def __init__(self, lines=()): self.lines = iter(lines)
        def readline(self, _: int = -1): return next(self.lines, "")
        def write(self, value: str): writes.append(value); return len(value)
        def flush(self): pass
    class Process:
        def __init__(self):
            ready = {"type":"ready", "interpreter_path":str(interpreter.resolve()), "artifact_sha256":chain["artifact_sha256"],
                     "artifact_size_bytes":chain["artifact_size_bytes"], "engine":"llama_cpp"}
            self.stdin=Pipe(); self.stdout=Pipe(["SENTIENTOS_LOCAL_MODEL_WORKER="+json.dumps(ready)+"\n",
                "SENTIENTOS_LOCAL_MODEL_WORKER="+json.dumps({"type":"generated","output":"bounded"})+"\n",
                "SENTIENTOS_LOCAL_MODEL_WORKER="+json.dumps({"type":"shutdown"})+"\n"]); self.stderr=Pipe(); self.closed=False
        def poll(self): return None if not self.closed else 0
        def wait(self, timeout=None): self.closed=True; return 0
        def terminate(self): self.closed=True
        def kill(self): self.closed=True
    process = Process(); captured: dict[str, object] = {}
    def popen(argv, **kwargs): captured.update(argv=argv, kwargs=kwargs); return process
    monkeypatch.setattr("sentientos.local_model_runtime_worker.subprocess.Popen", popen)
    monkeypatch.setenv("PYTHONPATH", "ambient"); monkeypatch.setenv("VIRTUAL_ENV", "ambient")
    worker = ExactRuntimeLocalModel(chain, route_load_configuration(chain))
    assert captured["argv"][0] == str(interpreter.resolve())  # type: ignore[index]
    assert "PYTHONPATH" not in captured["kwargs"]["env"] and "VIRTUAL_ENV" not in captured["kwargs"]["env"]  # type: ignore[index]
    assert worker.generate("hello") == "bounded"
    with pytest.raises(ModelLoadError, match="request too large"): worker.generate("x" * MAX_PROTOCOL_BYTES)
    worker.close(); assert json.loads(writes[-1])["type"] == "shutdown" and process.closed
    assert "NO_PROXY" in _environment()


def test_invalid_configured_production_activation_fails_closed_serving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    activation = tmp_path / "invalid.json"; activation.write_text("{}")
    monkeypatch.setenv("SENTIENTOS_LOCAL_MODEL_ACTIVATION", str(activation))
    monkeypatch.setattr("sentientos.local_model.LocalModel.autoload", lambda: (_ for _ in ()).throw(AssertionError("no fallback")))
    import importlib, sentientos.chat_service as chat
    chat = importlib.reload(chat)
    with pytest.raises(ProductionCommissioningError): chat._get_model()


def test_production_commission_activate_and_serve_governed_chat_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Composed synthetic witness of the authority-bearing orchestration, without real weights."""
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic"); chain = _chain(model, Path("/exact/runtime/python"))
    # Upstream canonical reconstruction is independently exercised by the substitution tests; this
    # injected sealed-chain boundary keeps this vertical witness deterministic and weight-free.
    monkeypatch.setattr("sentientos.local_model_production_commissioning.revalidate_chain", lambda value: dict(value))
    compatibility = _compat(chain)
    plan = compose_commissioning_plan(chain, compatibility, tmp_path / "commissioned")
    authorization = authorization_for(plan, operator_confirmed_plan_digest=plan["commissioning_plan_digest"])
    created: list[object] = []
    def factory(config):
        instance = _fake_model(config, ["smoke-ok", "chat-ok"]); created.append(instance); return instance
    receipt = commission(plan, compatibility, authorization, model_factory=factory)
    assert receipt["status"] == "local_model_commissioned" and receipt["activated"] is False
    assert receipt["smoke_inference_count"] == 1 and created[0].calls == ["Reply with one short confirmation token."]
    active_path = tmp_path / "active.json"; activation = activate(receipt, active_path)
    assert activation["status"] == "local_model_activated" and active_path.exists()
    # Serving reuses the exact commissioned identity/authority while remaining governed.
    from sentientos.local_model_authority import build_local_model_authority_map
    from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
    serving = created[0]
    authority = build_local_model_authority_map(serving.config, allowed_roots=[model.parent],
                                                observed_at="1970-01-01T00:00:00+00:00")
    invoker = GovernedLocalModelInvoker(model=serving, authority_map=authority, runtime_root=tmp_path / "chat")
    request = invoker.build_request(purpose="local_user_chat", prompt="hello", caller="chat_service", correlation_id="chat:e2e")
    chat_receipt = invoker.invoke(request)
    assert chat_receipt.status == "admitted_completed" and chat_receipt.output_text == "chat-ok"
    assert serving.active_identity.to_dict() == receipt["active_model_identity"]
    assert all(not value for key, value in chat_receipt.effects.items() if key != "local_model_inference")
    assert receipt["provider_network"] is receipt["tool"] is receipt["memory"] is receipt["action"] is False
