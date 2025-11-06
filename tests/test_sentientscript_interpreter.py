from __future__ import annotations

import base64
import pytest

from nacl.signing import SigningKey

from node_registry import NodeRegistry

from sentientscript import (
    ExecutionHistory,
    ScriptExecutionError,
    ScriptSigner,
    SentientScriptInterpreter,
)

import sentientscript.interpreter as ss_module

from sentient_shell import compile_command


class _StorageStub:
    def __init__(self) -> None:
        self.fragments: list[dict] = []

    def save_fragment(self, entry: dict) -> None:
        self.fragments.append(entry)


@pytest.fixture
def temp_interpreter(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path / "data"))
    registry_path = tmp_path / "registry.json"
    registry = NodeRegistry(registry_path)
    signing_key = SigningKey.generate()
    signer = ScriptSigner(registry)
    signer._signing_key = signing_key  # type: ignore[attr-defined]
    history = ExecutionHistory(root=tmp_path / "history")
    storage = _StorageStub()
    interpreter = SentientScriptInterpreter(signer=signer, history=history, storage=storage)
    interpreter.registry.register(
        "dream.new",
        lambda ctx, params: {"goal": params.get("goal"), "status": "queued"},
        capability="relay.dream",
    )
    interpreter.registry.register(
        "relay.echo",
        lambda ctx, params: {"echo": params},
        capability="relay.echo",
    )
    interpreter.registry.register(
        "actuator.shell",
        lambda ctx, params: {"ok": True, "cmd": params.get("cmd")},
        capability="actuator.shell",
    )
    return interpreter


def test_round_trip_shell_to_execution_replay(temp_interpreter):
    script = compile_command('dream.new goal="Explore"')
    temp_interpreter.signer.sign(script)
    result = temp_interpreter.execute(script)
    replay = temp_interpreter.replay(script, result.log)
    assert replay.fingerprint == result.fingerprint
    assert replay.outputs == result.outputs


def test_capability_sandbox_forbids_unlisted_action(temp_interpreter):
    script = {
        "id": "test-capability",
        "capabilities": ["relay.echo"],
        "steps": [
            {
                "type": "action",
                "name": "actuator.shell",
                "params": {"cmd": "echo hi"},
            }
        ],
    }
    with pytest.raises(ScriptExecutionError):
        temp_interpreter.execute(script)


def test_signed_plan_verification_between_trusted_nodes(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path / "data"))
    registry = NodeRegistry(tmp_path / "nodes.json")
    local_key = SigningKey.generate()
    signer = ScriptSigner(registry)
    signer._signing_key = local_key  # type: ignore[attr-defined]
    history = ExecutionHistory(root=tmp_path / "history")
    storage = _StorageStub()
    interpreter = SentientScriptInterpreter(signer=signer, history=history, storage=storage)
    interpreter.registry.register(
        "relay.echo",
        lambda ctx, params: {"echo": params},
        capability="relay.echo",
    )
    local_script = compile_command('relay.echo text="audit"')
    signer.sign(local_script, author="local-node")
    assert interpreter.signer.verify(local_script)

    remote_key = SigningKey.generate()
    remote_signer = ScriptSigner(registry)
    remote_signer._signing_key = remote_key  # type: ignore[attr-defined]
    remote_script = compile_command('relay.echo text="remote"')
    remote_signer.sign(remote_script, author="remote-node")
    assert interpreter.signer.verify(remote_script)

    payload = ss_module._script_payload(remote_script)
    signature_bytes = base64.b64decode(remote_script["signature"])
    assert remote_key.verify_key.verify(
        ss_module._canonical_json(payload).encode("utf-8"), signature_bytes
    )
