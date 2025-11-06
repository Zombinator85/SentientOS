"""Sentient Script interpreter, signing, and history helpers."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml  # type: ignore[import-untyped]
from nacl.signing import SigningKey, VerifyKey

import pairing_service
import secure_memory_storage
from node_registry import NodeRegistry, registry as global_registry
from sentientos.storage import get_data_root


@dataclass
class RegisteredAction:
    """Descriptor for a registered action."""

    name: str
    handler: Callable[["ExecutionContext", Dict[str, Any]], Dict[str, Any]]
    capability: Optional[str] = None


class ActionRegistry:
    """Registry of Sentient Script actions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._actions: Dict[str, RegisteredAction] = {}

    def register(
        self,
        name: str,
        handler: Callable[["ExecutionContext", Dict[str, Any]], Dict[str, Any]],
        *,
        capability: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._actions[name] = RegisteredAction(name=name, handler=handler, capability=capability)

    def unregister(self, name: str) -> None:
        with self._lock:
            self._actions.pop(name, None)

    def get(self, name: str) -> RegisteredAction:
        with self._lock:
            try:
                return self._actions[name]
            except KeyError as exc:  # pragma: no cover - defensive
                raise ScriptExecutionError(f"Unknown action: {name}") from exc

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._actions.keys())


class ScriptExecutionError(RuntimeError):
    """Raised when a Sentient Script cannot complete successfully."""

    def __init__(self, message: str, *, path: Optional[str] = None) -> None:
        super().__init__(message)
        self.path = path


@dataclass
class ExecutionResult:
    """Result of executing a script."""

    script_id: str
    run_id: str
    outputs: Dict[str, Any]
    log: List[Dict[str, Any]]
    fingerprint: str
    completed: bool
    signed_by: Optional[str]
    signature: Optional[str]


class ExecutionHistory:
    """Persist minimal execution history and safety shadows."""

    def __init__(self, *, root: Optional[Path] = None) -> None:
        base = Path(root) if root else get_data_root() / "scripts"
        self._history_path = base / "history.jsonl"
        self._logs_dir = base / "logs"
        self._lock = threading.RLock()
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    def append_entry(self, entry: Mapping[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            if self._history_path.exists():
                existing = self._history_path.read_text(encoding="utf-8").rstrip("\n")
                payload = f"{existing}\n{line}" if existing else line
            else:
                payload = line
            self._history_path.write_text(payload + "\n", encoding="utf-8")

    def record_log(self, run_id: str, events: Sequence[Mapping[str, Any]]) -> None:
        path = self._logs_dir / f"{run_id}.json"
        payload = {"run_id": run_id, "events": list(events)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_entries(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        if not self._history_path.exists():
            return []
        lines = [line for line in self._history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        records: List[Dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.append(data)
        return records

    def load_shadow(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = self._logs_dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        events: List[Dict[str, Any]] = []
        for item in payload.get("events", []):
            if not isinstance(item, dict):
                continue
            events.append(
                {
                    "path": item.get("path"),
                    "type": item.get("type"),
                    "status": item.get("status"),
                    "attempt": item.get("attempt"),
                    "timestamp": item.get("timestamp"),
                }
            )
        return {"run_id": run_id, "events": events}


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _script_payload(script: Mapping[str, Any]) -> Dict[str, Any]:
    data = dict(script)
    data.pop("signature", None)
    data.pop("signed_by", None)
    return data


class ScriptSigner:
    """Sign and verify Sentient Script payloads."""

    def __init__(self, registry: NodeRegistry | None = None) -> None:
        self._registry = registry or global_registry
        self._lock = threading.RLock()
        self._signing_key: SigningKey | None = None

    def _load_signing_key(self) -> SigningKey:
        with self._lock:
            if self._signing_key is None:
                service = pairing_service.PairingService()
                self._signing_key = service._signing_key  # pylint: disable=protected-access
            return self._signing_key

    @staticmethod
    def _signature_input(script: Mapping[str, Any]) -> bytes:
        return _canonical_json(_script_payload(script)).encode("utf-8")

    def _ensure_registry_entry(self, hostname: str, verify_key: VerifyKey) -> None:
        fingerprint = hashlib.sha256(verify_key.encode()).hexdigest()
        capabilities = {"sentientscript_pubkey": base64.b64encode(verify_key.encode()).decode("ascii")}
        existing = self._registry.get(hostname)
        roles: Iterable[str] | None = None
        ip = "127.0.0.1"
        port = 5000
        trust = "trusted"
        if existing is not None:
            roles = existing.roles
            capabilities.update(existing.capabilities)
            ip = existing.ip
            port = existing.port
            trust = existing.trust_level
        self._registry.register_or_update(
            hostname,
            ip,
            port=port,
            capabilities=capabilities,
            trust_level=trust,
            pubkey_fingerprint=fingerprint,
            roles=roles,
        )
        self._registry.set_local_identity(hostname)

    def sign(self, script: Dict[str, Any], *, author: Optional[str] = None) -> Dict[str, Any]:
        signing_key = self._load_signing_key()
        hostname = author or os.getenv("SENTIENTOS_HOSTNAME") or os.getenv("HOSTNAME") or os.uname().nodename
        self._ensure_registry_entry(hostname, signing_key.verify_key)
        signature = signing_key.sign(self._signature_input(script)).signature
        script["signature"] = base64.b64encode(signature).decode("ascii")
        script["signed_by"] = hostname
        return script

    def verify(self, script: Mapping[str, Any]) -> bool:
        signature = script.get("signature")
        signer = script.get("signed_by")
        if not isinstance(signature, str) or not signature:
            return False
        if not isinstance(signer, str) or not signer:
            return False
        record = self._registry.get(signer)
        if record is None:
            return False
        pubkey = record.capabilities.get("sentientscript_pubkey")
        if not isinstance(pubkey, str) or not pubkey:
            return False
        try:
            verify_key = VerifyKey(base64.b64decode(pubkey))
            verify_key.verify(self._signature_input(script), base64.b64decode(signature))
        except Exception:  # pragma: no cover - invalid key or signature
            return False
        return True


@dataclass
class ExecutionContext:
    script: Mapping[str, Any]
    rng: "random.Random"
    registry: ActionRegistry
    timeout: float
    gas: int
    capabilities: Sequence[str]
    start_monotonic: float
    replay_cursor: Optional["ReplayCursor"]
    outputs: Dict[str, Any]
    log: List[Dict[str, Any]]

    def check_limits(self, path: str) -> None:
        elapsed = time.monotonic() - self.start_monotonic
        if self.timeout and elapsed > self.timeout:
            raise ScriptExecutionError("script timed out", path=path)
        if self.gas <= 0:
            raise ScriptExecutionError("gas exhausted", path=path)
        self.gas -= 1

    def record(self, event: Mapping[str, Any]) -> None:
        self.log.append(dict(event))


class ReplayCursor:
    """Iterate through recorded events during deterministic replay."""

    def __init__(self, events: Sequence[Mapping[str, Any]]) -> None:
        self._events = list(events)
        self._index = 0

    def expect(self, path: str, event_type: str, *, attempt: Optional[int] = None) -> Mapping[str, Any]:
        if self._index >= len(self._events):
            raise ScriptExecutionError("replay log exhausted", path=path)
        event = self._events[self._index]
        self._index += 1
        if event.get("path") != path or event.get("type") != event_type:
            raise ScriptExecutionError("replay divergence detected", path=path)
        if attempt is not None and event.get("attempt") != attempt:
            raise ScriptExecutionError("replay attempt mismatch", path=path)
        return event


def _sanitize_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in result.items():
        if key in {"stdout", "stderr", "logs"}:
            continue
        sanitized[key] = value
    return sanitized


class SentientScriptInterpreter:
    """Interpret and execute Sentient Script plans."""

    def __init__(
        self,
        *,
        registry: ActionRegistry | None = None,
        signer: ScriptSigner | None = None,
        history: ExecutionHistory | None = None,
        storage: Any | None = None,
    ) -> None:
        self.registry = registry or ActionRegistry()
        self.signer = signer or ScriptSigner()
        self.history = history or ExecutionHistory()
        self.storage = storage or secure_memory_storage
        self._register_defaults()

    def _register_defaults(self) -> None:
        def _record_goal(context: ExecutionContext, params: Dict[str, Any]) -> Dict[str, Any]:
            goal = str(params.get("goal", "")).strip()
            if not goal:
                raise ScriptExecutionError("goal text required", path=context.outputs.get("__current_path", ""))
            return {"goal": goal, "status": "queued", "recorded_at": time.time()}

        def _local_echo(context: ExecutionContext, params: Dict[str, Any]) -> Dict[str, Any]:
            return {"echo": params}

        self.registry.register("dream.new", _record_goal, capability="relay.dream")
        self.registry.register("relay.echo", _local_echo, capability="relay.echo")

    @staticmethod
    def load_script(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, Mapping):
            return dict(payload)
        if isinstance(payload, str):
            payload = payload.strip()
            if not payload:
                return {}
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                data = yaml.safe_load(payload)
                if isinstance(data, Mapping):
                    return dict(data)
                raise ScriptExecutionError("Unsupported script payload")
        raise ScriptExecutionError("Unsupported script payload type")

    def _prepare_context(
        self,
        script: Mapping[str, Any],
        *,
        replay_log: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> ExecutionContext:
        import random

        seed = script.get("seed")
        if isinstance(seed, int):
            rng = random.Random(seed)
        else:
            seed = int.from_bytes(os.urandom(8), "big")
            rng = random.Random(seed)
            script.setdefault("seed", seed)
        timeout = float(script.get("timeout", 30.0))
        gas = int(script.get("gas", 128))
        capabilities = list(script.get("capabilities", []))
        return ExecutionContext(
            script=script,
            rng=rng,
            registry=self.registry,
            timeout=timeout,
            gas=gas,
            capabilities=capabilities,
            start_monotonic=time.monotonic(),
            replay_cursor=ReplayCursor(replay_log) if replay_log else None,
            outputs={},
            log=[],
        )

    def _require_capability(self, context: ExecutionContext, capability: Optional[str], path: str) -> None:
        if capability and capability not in context.capabilities:
            raise ScriptExecutionError(f"missing capability: {capability}", path=path)

    def _execute_action(self, context: ExecutionContext, node: Mapping[str, Any], path: str) -> Dict[str, Any]:
        name = str(node.get("name") or node.get("action") or "").strip()
        if not name:
            raise ScriptExecutionError("action name required", path=path)
        action = context.registry.get(name)
        self._require_capability(context, action.capability, path)
        params = node.get("params")
        payload = dict(params) if isinstance(params, Mapping) else {}
        context.outputs["__current_path"] = path
        if context.replay_cursor:
            recorded = dict(
                context.replay_cursor.expect(
                    path,
                    "action",
                    attempt=int(node.get("attempt", 1)),
                )
            )
            context.record(recorded)
            result = recorded.get("result", {})
            context.outputs[path] = result
            return result  # type: ignore[return-value]
        event: Dict[str, Any] = {
            "path": path,
            "type": "action",
            "name": name,
            "params": payload,
            "timestamp": time.time(),
            "attempt": int(node.get("attempt", 1)),
        }
        try:
            result = action.handler(context, payload)
            if not isinstance(result, Mapping):
                result = {"result": result}
            sanitized = _sanitize_result(dict(result))
            event["result"] = sanitized
            event["status"] = "ok"
            context.record(event)
            context.outputs[path] = sanitized
            return sanitized
        except ScriptExecutionError:
            raise
        except Exception as exc:
            event["status"] = "error"
            event["error"] = str(exc)
            context.record(event)
            raise ScriptExecutionError(str(exc), path=path) from exc

    def _execute_sequence(self, context: ExecutionContext, node: Mapping[str, Any], path: str) -> Any:
        steps = node.get("steps")
        if not isinstance(steps, Sequence):
            raise ScriptExecutionError("sequence requires steps", path=path)
        result: Any = None
        for index, child in enumerate(steps):
            result = self._execute_node(context, child, f"{path}/{index}")
        return result

    def _execute_choice(self, context: ExecutionContext, node: Mapping[str, Any], path: str) -> Any:
        options = node.get("options")
        if not isinstance(options, Sequence) or not options:
            raise ScriptExecutionError("choice requires options", path=path)
        weights: List[float] = []
        total = 0.0
        for option in options:
            weight = 1.0
            if isinstance(option, Mapping):
                try:
                    weight = float(option.get("weight", 1.0))
                except (TypeError, ValueError):
                    weight = 1.0
            weights.append(max(weight, 0.0))
            total += max(weight, 0.0)
        recorded_choice: Dict[str, Any] | None = None
        if context.replay_cursor:
            recorded_choice = dict(context.replay_cursor.expect(path, "choice"))
            index = int(recorded_choice.get("selected", 0))
        else:
            pick = context.rng.uniform(0, total) if total > 0 else 0
            running = 0.0
            index = 0
            for idx, weight in enumerate(weights):
                running += weight
                if pick <= running:
                    index = idx
                    break
        if recorded_choice is not None:
            context.record(recorded_choice)
        else:
            event = {"path": path, "type": "choice", "selected": index, "timestamp": time.time(), "status": "ok"}
            context.record(event)
        selected = options[index]
        return self._execute_node(context, selected, f"{path}/{index}")

    def _execute_retry(self, context: ExecutionContext, node: Mapping[str, Any], path: str) -> Any:
        step = node.get("step")
        if not isinstance(step, Mapping):
            raise ScriptExecutionError("retry requires step", path=path)
        max_attempts = int(node.get("max_attempts", 3))
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            attempt_node = dict(step)
            attempt_node["attempt"] = attempt
            try:
                return self._execute_node(context, attempt_node, path)
            except ScriptExecutionError as exc:
                last_error = exc
                if context.replay_cursor:
                    recorded_retry = dict(
                        context.replay_cursor.expect(path, "retry", attempt=attempt)
                    )
                    context.record(recorded_retry)
                else:
                    event = {
                        "path": path,
                        "type": "retry",
                        "status": "failed",
                        "attempt": attempt,
                        "timestamp": time.time(),
                        "error": str(exc),
                    }
                    context.record(event)
        if last_error is not None:
            raise ScriptExecutionError(str(last_error), path=path) from last_error
        raise ScriptExecutionError("retry failed", path=path)

    def _execute_end(self, context: ExecutionContext, node: Mapping[str, Any], path: str) -> Any:
        value = node.get("value")
        if context.replay_cursor:
            recorded = dict(context.replay_cursor.expect(path, "end"))
            context.record(recorded)
            context.outputs[path] = recorded.get("value")
            return recorded.get("value")
        event = {"path": path, "type": "end", "timestamp": time.time(), "status": "ok", "value": value}
        context.record(event)
        context.outputs[path] = value
        return value

    def _execute_node(self, context: ExecutionContext, node: Any, path: str) -> Any:
        context.check_limits(path)
        if isinstance(node, Mapping):
            node_type = str(node.get("type") or "action").lower()
            if node_type == "action":
                return self._execute_action(context, node, path)
            if node_type == "sequence":
                return self._execute_sequence(context, node, path)
            if node_type == "choice":
                return self._execute_choice(context, node, path)
            if node_type == "retry":
                return self._execute_retry(context, node, path)
            if node_type == "end":
                return self._execute_end(context, node, path)
            raise ScriptExecutionError(f"unknown node type: {node_type}", path=path)
        if isinstance(node, Sequence):
            return self._execute_sequence(context, {"type": "sequence", "steps": list(node)}, path)
        raise ScriptExecutionError("invalid script node", path=path)

    def _fingerprint(self, script: Mapping[str, Any], log: Sequence[Mapping[str, Any]]) -> str:
        hasher = hashlib.sha256()
        hasher.update(_canonical_json(_script_payload(script)).encode("utf-8"))
        hasher.update(_canonical_json({"events": list(log)}).encode("utf-8"))
        return hasher.hexdigest()

    def execute(
        self,
        payload: Any,
        *,
        replay_log: Optional[Sequence[Mapping[str, Any]]] = None,
        verify_signature: bool = True,
    ) -> ExecutionResult:
        script = self.load_script(payload)
        if verify_signature and script.get("signature"):
            if not self.signer.verify(script):
                raise ScriptExecutionError("signature verification failed", path="root")
        context = self._prepare_context(script, replay_log=replay_log)
        steps = script.get("steps")
        if not isinstance(steps, Sequence):
            raise ScriptExecutionError("script requires steps", path="root")
        result: Any = None
        for index, node in enumerate(steps):
            result = self._execute_node(context, node, f"root/{index}")
        fingerprint = self._fingerprint(script, context.log)
        run_id = f"{script.get('id', 'script')}::{uuid.uuid4()}"
        entry = {
            "script_id": script.get("id", "script"),
            "run_id": run_id,
            "timestamp": time.time(),
            "fingerprint": fingerprint,
            "status": "completed" if not replay_log else "replayed",
            "signed_by": script.get("signed_by"),
        }
        self.history.append_entry(entry)
        self.history.record_log(run_id, context.log)
        fragment = {
            "id": fingerprint,
            "timestamp": time.time(),
            "category": "sentientscript",
            "importance": 0.1,
            "data": {
                "script_id": script.get("id"),
                "run_id": run_id,
                "summary": result,
            },
        }
        try:
            self.storage.save_fragment(fragment)
        except Exception:  # pragma: no cover - secure storage optional
            pass
        return ExecutionResult(
            script_id=str(script.get("id", "")),
            run_id=run_id,
            outputs=context.outputs,
            log=context.log,
            fingerprint=fingerprint,
            completed=True,
            signed_by=script.get("signed_by"),
            signature=script.get("signature"),
        )

    def replay(self, payload: Any, log: Sequence[Mapping[str, Any]]) -> ExecutionResult:
        return self.execute(payload, replay_log=log)

    def build_shadow(self, *, kind: str, text: str) -> Dict[str, Any]:
        script = {
            "id": f"shadow-{kind}-{uuid.uuid4().hex[:8]}",
            "version": "1.0",
            "seed": int.from_bytes(os.urandom(4), "big"),
            "timeout": 5.0,
            "gas": 16,
            "capabilities": ["relay.echo"],
            "metadata": {"origin": kind, "created_at": time.time()},
            "steps": [
                {
                    "type": "action",
                    "name": "relay.echo",
                    "params": {"text": text},
                }
            ],
        }
        self.signer.sign(script)
        return script


def list_script_history(*, limit: int = 20, history: ExecutionHistory | None = None) -> List[Dict[str, Any]]:
    hist = history or ExecutionHistory()
    return hist.list_entries(limit=limit)


def load_safety_shadow(run_id: str, *, history: ExecutionHistory | None = None) -> Optional[Dict[str, Any]]:
    hist = history or ExecutionHistory()
    return hist.load_shadow(run_id)
