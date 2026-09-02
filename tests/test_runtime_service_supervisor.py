from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.chat_service import PersistentConversationService
from sentientos.conversation_session import ConversationSessionStore
from sentientos.runtime.services import HealthResult, InProcessServiceAdapter
from sentientos.runtime.supervisor import RuntimeServiceDescriptor, RuntimeSupervisor, ServiceRegistry

pytestmark = pytest.mark.no_legacy_skip


class Fake:
    def __init__(self, name: str, events: list[str], *, ready: bool = True) -> None:
        self.name, self.events, self.ready = name, events, ready
        self.starts = self.stops = self.forces = 0
    @property
    def identity(self): return {"name": self.name}
    def start(self): self.starts += 1; self.events.append("start:" + self.name)
    def health(self): return HealthResult(self.ready, "ready" if self.ready else "failed")
    def stop(self): self.stops += 1; self.events.append("stop:" + self.name)
    def force_stop(self): self.forces += 1; self.events.append("force:" + self.name)


def descriptor(name: str, dependencies: tuple[str, ...] = (), *, budget: int = 2, **kw):
    return RuntimeServiceDescriptor(name, name, "test", dependencies, restart_budget=budget,
                                    min_backoff=0, max_backoff=0, **kw)


def registry(*rows):
    value = ServiceRegistry()
    for desc, adapter in rows: value.register(desc, adapter)
    return value


def test_deterministic_dependency_startup_order(tmp_path: Path) -> None:
    events: list[str] = []; a, b, c = Fake("a", events), Fake("b", events), Fake("c", events)
    sup = RuntimeSupervisor(registry((descriptor("c", ("a", "b")), c), (descriptor("b"), b), (descriptor("a"), a)), state_root=tmp_path)
    assert sup.registry.startup_order() == ("a", "b", "c")
    sup.start_all(); assert events == ["start:a", "start:b", "start:c"]


def test_registry_rejections() -> None:
    events: list[str] = []; r = ServiceRegistry(); r.register(descriptor("a"), Fake("a", events))
    with pytest.raises(ValueError, match="duplicate"): r.register(descriptor("a"), Fake("x", events))
    bad = registry((descriptor("a", ("missing",)), Fake("a", events)))
    with pytest.raises(ValueError, match="unknown"): bad.freeze()
    cyc = registry((descriptor("a", ("b",)), Fake("a", events)), (descriptor("b", ("a",)), Fake("b", events)))
    with pytest.raises(ValueError, match="cycle"): cyc.freeze()


def test_missing_dependency_degrades_without_restart_storm_and_recovers(tmp_path: Path) -> None:
    events: list[str] = []; dependency, child = Fake("dep", events, ready=False), Fake("child", events)
    sup = RuntimeSupervisor(registry((descriptor("dep", budget=0), dependency), (descriptor("child", ("dep",)), child)), state_root=tmp_path)
    sup.start_all(); sup.observe(); sup.observe()
    assert sup.status()["services"]["child"]["state"] == "degraded" and child.starts == 0
    dependency.ready = True; sup.reset_restart_budget("dep"); sup.start_all(); sup.observe()
    assert sup.status()["services"]["child"]["state"] == "healthy" and child.starts == 1


def test_restart_budget_exhaustion_and_no_further_automatic_restart(tmp_path: Path) -> None:
    events: list[str] = []; service = Fake("svc", events)
    sup = RuntimeSupervisor(registry((descriptor("svc", budget=1), service)), state_root=tmp_path)
    sup.start_all(); service.ready = False; sup.observe(); assert service.starts == 2
    sup.observe(); starts = service.starts; sup.observe()
    state = sup.status()["services"]["svc"]
    assert state["state"] == "failed" and state["restart_budget_exhausted"] and service.starts == starts
    sup.reset_restart_budget("svc"); service.ready = True; sup.start_all(); assert service.starts == starts + 1


def test_restart_budget_persists_across_supervisor_reconstruction(tmp_path: Path) -> None:
    events: list[str] = []; first = Fake("svc", events)
    sup = RuntimeSupervisor(registry((descriptor("svc", budget=1), first)), state_root=tmp_path)
    sup.start_all(); first.ready = False; sup.observe(); sup.observe()
    second = Fake("svc", events)
    rebuilt = RuntimeSupervisor(registry((descriptor("svc", budget=1), second)), state_root=tmp_path)
    assert rebuilt.status()["services"]["svc"]["restart_budget_exhausted"] is True
    rebuilt.observe(); assert second.starts == 0


def test_panic_prevents_restart_and_requires_explicit_clear(tmp_path: Path) -> None:
    events: list[str] = []; service = Fake("svc", events)
    sup = RuntimeSupervisor(registry((descriptor("svc"), service)), state_root=tmp_path)
    sup.start_all(); sup.panic_stop(); service.ready = False; sup.observe()
    assert sup.status()["panic_latched"] and service.starts == 1
    with pytest.raises(RuntimeError, match="panic"): sup.start_all()
    rebuilt = RuntimeSupervisor(registry((descriptor("svc"), Fake("svc", events))), state_root=tmp_path)
    with pytest.raises(RuntimeError, match="panic"): rebuilt.start_all()
    rebuilt.clear_panic(); rebuilt.start_all(); assert not rebuilt.status()["panic_latched"]


def test_reverse_shutdown_and_forced_timeout(tmp_path: Path) -> None:
    events: list[str] = []; a, b = Fake("a", events), Fake("b", events)
    sup = RuntimeSupervisor(registry((descriptor("a"), a), (descriptor("b", ("a",)), b)), state_root=tmp_path / "one")
    sup.start_all(); events.clear(); sup.shutdown(); assert events == ["stop:b", "stop:a"]
    slow = Fake("slow", events)
    def delayed(): time.sleep(.05)
    slow.stop = delayed  # type: ignore[method-assign]
    sup2 = RuntimeSupervisor(registry((descriptor("slow", shutdown_timeout=.005), slow)), state_root=tmp_path / "two")
    sup2.start_all(); sup2.shutdown(); assert slow.forces == 1


def test_start_and_health_timeouts_and_corrupt_state_fail_closed(tmp_path: Path) -> None:
    events: list[str] = []; slow = Fake("slow", events)
    slow.start = lambda: time.sleep(.05)  # type: ignore[method-assign]
    sup = RuntimeSupervisor(registry((descriptor("slow", startup_timeout=.005), slow)), state_root=tmp_path / "start")
    sup.start_all(); assert sup.status()["services"]["slow"]["state"] == "failed"
    root = tmp_path / "corrupt"; root.mkdir(); (root / "supervisor-state.json").write_text("{")
    closed = RuntimeSupervisor(registry((descriptor("svc"), Fake("svc", events))), state_root=root)
    assert closed.status()["panic_latched"] is True


def test_concurrent_status_reads_are_safe(tmp_path: Path) -> None:
    events: list[str] = []; sup = RuntimeSupervisor(registry((descriptor("svc"), Fake("svc", events))), state_root=tmp_path)
    sup.start_all(); errors: list[Exception] = []
    def read():
        try:
            for _ in range(100): sup.status()
        except Exception as exc: errors.append(exc)
    threads = [threading.Thread(target=read) for _ in range(4)]
    [x.start() for x in threads]; sup.observe(); [x.join() for x in threads]
    assert not errors


class Identity:
    def to_dict(self): return {"model_id": "commissioned-synthetic", "route_id": "test", "posture": "production"}
class Invoker:
    def __init__(self): self.model = SimpleNamespace(active_identity=Identity()); self.requests = []
    def build_request(self, **kw):
        request = SimpleNamespace(**kw, request_id="synthetic-request"); self.requests.append(request); return request
    def invoke(self, request):
        return SimpleNamespace(status="admitted_completed", output_text="synthetic answer", request={"request_id": request.request_id}, receipt_digest="synthetic-receipt")
class ChatAdapter:
    def __init__(self, root: Path): self.root = root; self.app = None; self.alive = False; self.starts = 0; self.invokers = []
    @property
    def identity(self): return {"kind": "persistent_governed_chat", "model": "commissioned-synthetic"}
    def start(self):
        invoker = Invoker(); self.invokers.append(invoker); self.app = PersistentConversationService(invoker=invoker,
            session_store=ConversationSessionStore(self.root / "conversations"), memory_store=CanonicalMemoryStore(self.root / "memory")); self.alive = True; self.starts += 1
    def health(self): return HealthResult(self.alive and self.app is not None, "chat_store_and_commissioned_invoker_ready" if self.alive else "chat_surface_failed")
    def stop(self): self.alive = False
    def force_stop(self): self.alive = False


def test_persistent_chat_restart_resume_successful_path(tmp_path: Path) -> None:
    chat = ChatAdapter(tmp_path / "data")
    sup = RuntimeSupervisor(registry((descriptor("commissioned", restart_policy="never"), Fake("commissioned", [])),
        (descriptor("chat", ("commissioned",), budget=2), chat)), state_root=tmp_path / "state")
    sup.start_all(); first = chat.app.chat("Remember my project is Aurora", retain=True)
    chat.alive = False; sup.observe()
    assert chat.starts == 2 and sup.status()["services"]["chat"]["restart_count"] == 1
    resumed = chat.app.chat("What was my project?", session_id=first.session_id)
    prompt = chat.invokers[-1].requests[0].prompt
    loaded = chat.app.sessions.load(resumed.session_id)
    assert "project is Aurora" in prompt and chat.app.memories.retrieve("Aurora")["memories"]
    assert loaded["model_identity"]["model_id"] == "commissioned-synthetic"
    assert [x["role"] for x in loaded["turns"]] == ["user", "assistant", "user", "assistant"]
    persisted = json.loads((tmp_path / "state/supervisor-state.json").read_text())
    assert len(persisted["restart_histories"]["chat"]) == 1
