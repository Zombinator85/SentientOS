# mypy: disable-error-code=untyped-decorator
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Mapping, Protocol

from .fastapi_stub import FastAPI, HTMLResponse, HTTPException

if TYPE_CHECKING:
    class BaseModel:
        def __init__(self, **data: object) -> None: ...
else:
    from pydantic import BaseModel

from .change_narrator import ChangeNarrator, build_default_change_narrator
from .event_stream import history as boot_history
from .governed_local_model_invocation import GovernedLocalModelInvoker
from .governed_local_model_invocation import LocalModelInvocationReceipt
from .installation_state import InstallationIdentity, InstallationStateRegistry
from .control_plane_kernel import ControlPlaneKernel
from .local_model_production_serving import ProductionServingController
from .local_model_serving_inference import ProductionServingInferenceController
from .conversation_session import ConversationSessionStore, assemble_local_chat_context
from .canonical_memory import (AdmittedRetentionWriter, CanonicalMemoryStore, CANDIDATE_TYPE,
    ExplicitRetentionAdmissionGate, sentientos_data_dir)
from .governed_local_model_invocation import LocalModelInvocationBudget

LOGGER = logging.getLogger(__name__)
APP = FastAPI(title="SentientOS Chat", version="1.0")
_CONVERSATION_SERVICE: "PersistentConversationService | None" = None
_PRODUCTION_COMPOSITION: "ProductionChatComposition | None" = None
try:
    _CHANGE_NARRATOR: ChangeNarrator | None = build_default_change_narrator()
except Exception:  # pragma: no cover - defensive initialization
    LOGGER.exception("Unable to initialise change narrator")
    _CHANGE_NARRATOR = None




class ChatInference(Protocol):
    def current_conversation_model_identity(self) -> Mapping[str, Any]: ...
    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget,
                 caller_linkage: Mapping[str, Any]) -> LocalModelInvocationReceipt: ...


class DevelopmentSimulationInference:
    """Affirmative test/development-only adapter; never selected by production."""
    __slots__ = ("_delegate",)
    def __init__(self, invoker: GovernedLocalModelInvoker) -> None:
        self._delegate = invoker
    def current_conversation_model_identity(self) -> Mapping[str, Any]:
        identity = getattr(self._delegate.model, "active_identity", None)
        return identity.to_dict() if identity is not None else {}
    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget,
                 caller_linkage: Mapping[str, Any]) -> LocalModelInvocationReceipt:
        request = self._delegate.build_request(purpose="local_user_chat", prompt=prompt, caller=caller,
            correlation_id=correlation_id, budget=budget, linkage=caller_linkage)
        return self._delegate.invoke(request)


class ProductionChatComposition:
    __slots__ = ("service", "_serving")
    def __init__(self, service: "PersistentConversationService", serving: ProductionServingController) -> None:
        self.service, self._serving = service, serving
    def close(self) -> None:
        self._serving.close()
    def ready(self) -> bool:
        return self._serving.serving_is_current()

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    retain: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    turn_id: str
    context: dict[str, object]
    retention: dict[str, object]


class PersistentConversationService:
    """One transaction boundary for durable turns and governed inference.

    A denied/failed invocation intentionally preserves the user turn as an
    unanswered turn and never manufactures an assistant turn.
    """
    def __init__(self, *, inference: ChatInference, session_store: ConversationSessionStore,
                 memory_store: CanonicalMemoryStore, context_budget_chars: int = 4000,
                 memory_budget_chars: int = 1600, admission_gate: ExplicitRetentionAdmissionGate | None = None) -> None:
        self._inference = inference; self.sessions = session_store; self.memories = memory_store
        self.admission_gate = admission_gate or ExplicitRetentionAdmissionGate()
        self.retention_writer = AdmittedRetentionWriter(memory_store)
        self.context_budget_chars = context_budget_chars; self.memory_budget_chars = memory_budget_chars

    def chat(self, message: str, *, session_id: str | None = None, retain: bool = False) -> ChatResponse:
        identity_payload = self._inference.current_conversation_model_identity()
        session = self.sessions.create(model_identity=identity_payload) if session_id is None else self.sessions.load(session_id)
        if session["model_identity_digest"] != __import__("hashlib").sha256(
            __import__("json").dumps(identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest():
            raise ValueError("session_model_identity_mismatch")
        user_turn = self.sessions.append_turn(session["session_id"], role="user", text=message,
                                              retention_state="requested" if retain else "not_requested")
        history = self.sessions.reconstruct(session["session_id"], budget_chars=self.context_budget_chars,
                                            exclude_turn_id=user_turn["turn_id"])
        memory = self.memories.retrieve(message, budget_chars=self.memory_budget_chars)
        prompt = assemble_local_chat_context(history=history, memory_snapshot=memory, current_message=message)
        linkage = {"session_id": session["session_id"], "user_turn_id": user_turn["turn_id"],
                   "conversation_context_snapshot_digest": history.snapshot_digest,
                   "memory_retrieval_snapshot_digest": memory["snapshot_digest"]}
        receipt = self._inference.generate(prompt=prompt, caller="chat_service",
            correlation_id=f"chat:{session['session_id']}:{user_turn['turn_id']}",
            budget=LocalModelInvocationBudget(max_input_chars=8000), caller_linkage=linkage)
        accepted_statuses = {"admitted_completed"}
        if isinstance(self._inference, DevelopmentSimulationInference):
            accepted_statuses.add("admitted_simulation")
        if receipt.status not in accepted_statuses or not receipt.output_text:
            raise RuntimeError(f"governed_inference_not_completed:{receipt.status}")
        assistant = self.sessions.append_turn(session["session_id"], role="assistant", text=receipt.output_text,
            linkage={"request_id": receipt.request.get("request_id"), "invocation_receipt_digest": receipt.receipt_digest,
                     "active_model_identity_digest": session["model_identity_digest"], "context_snapshot_digest": history.snapshot_digest,
                     "memory_snapshot_digest": memory["snapshot_digest"]})
        retention_result: dict[str, object] = {"status": "not_requested"}
        if retain:
            request_id = "retain-request-" + uuid.uuid4().hex[:24]
            candidate = {"candidate_type": CANDIDATE_TYPE, "session_id": session["session_id"],
                         "source_turn_id": user_turn["turn_id"], "source_role": "user",
                         "source_text_digest": user_turn["text_digest"], "explicitly_requested": True,
                         "request_id": request_id, "operation_id": "retain:" + session["session_id"] + ":" + user_turn["turn_id"]}
            admission = self.admission_gate.decide(candidate)
            try:
                if admission.decision != "retention_admitted": raise PermissionError(admission.reason or "retention_denied")
                retention_result = self.retention_writer.execute(candidate, admission, user_turn)
                self.sessions.update_turn_retention(session["session_id"], user_turn["turn_id"], state="retained", receipt=retention_result)
            except Exception as exc:
                retention_result = {"status": "retention_failed", "reason": str(exc),
                                    "admission_receipt_digest": admission.receipt_digest}
                self.sessions.update_turn_retention(session["session_id"], user_turn["turn_id"], state="retention_failed", receipt=retention_result)
        return ChatResponse(response=receipt.output_text, session_id=session["session_id"], turn_id=assistant["turn_id"],
                            context={"conversation_snapshot_digest": history.snapshot_digest,
                                     "memory_snapshot_digest": memory["snapshot_digest"],
                                     "selected_turn_count": len(history.turns), "selected_memory_count": len(memory["memories"])},
                            retention=retention_result)


def _get_conversation_service() -> PersistentConversationService:
    if _CONVERSATION_SERVICE is None:
        raise RuntimeError("chat_not_explicitly_configured")
    return _CONVERSATION_SERVICE


def configure_production_chat(*, installation_identity: str, serving_operation_id: str,
                              expected_activation_state_digest: str | None = None,
                              control_plane_kernel: ControlPlaneKernel | None = None) -> None:
    """Establish exactly one explicit hardened production serving lifetime."""
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    identity = InstallationIdentity.parse(installation_identity)
    handle = InstallationStateRegistry.system().open(identity)
    serving = ProductionServingController(handle, control_plane_kernel or ControlPlaneKernel())
    try:
        establish_arguments = {"operation_id": serving_operation_id}
        if expected_activation_state_digest is not None:
            establish_arguments["expected_activation_state_digest"] = expected_activation_state_digest
        serving.establish(**establish_arguments)
        inference = ProductionServingInferenceController(serving)
        data_root = sentientos_data_dir()
        service = PersistentConversationService(inference=inference,
            session_store=ConversationSessionStore(data_root / "conversations"),
            memory_store=CanonicalMemoryStore(data_root / "memory"))
    except Exception:
        serving.close()
        raise
    close_production_chat()
    _CONVERSATION_SERVICE = service
    _PRODUCTION_COMPOSITION = ProductionChatComposition(service, serving)


def configure_development_chat(*, invoker: GovernedLocalModelInvoker,
                               data_root: Path | None = None) -> None:
    """Explicitly install isolated echo/null/test inference."""
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    close_production_chat()
    root = data_root or sentientos_data_dir()
    _CONVERSATION_SERVICE = PersistentConversationService(
        inference=DevelopmentSimulationInference(invoker),
        session_store=ConversationSessionStore(root / "conversations"),
        memory_store=CanonicalMemoryStore(root / "memory"))
    _PRODUCTION_COMPOSITION = None


def close_production_chat() -> None:
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    composition = _PRODUCTION_COMPOSITION
    _PRODUCTION_COMPOSITION = None
    _CONVERSATION_SERVICE = None
    if composition is not None:
        composition.close()


def production_chat_ready() -> bool:
    """Return coarse read-only readiness; never establish or invoke a model."""
    composition = _PRODUCTION_COMPOSITION
    return composition is not None and composition.ready()


class BootEvent(BaseModel):
    timestamp: str
    message: str
    level: str


@APP.on_event("startup")
async def _startup_event() -> None:
    LOGGER.info("Chat interface ready")


@APP.on_event("shutdown")
async def _shutdown_event() -> None:
    close_production_chat()


@APP.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty")
    if _CHANGE_NARRATOR is not None:
        summary = _CHANGE_NARRATOR.maybe_respond(message)
        if summary is not None:
            # Narrator responses are not model conversation turns.
            raise HTTPException(status_code=409, detail=summary)
    try:
        return _get_conversation_service().chat(message, session_id=request.session_id, retain=request.retain)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        LOGGER.warning("Production chat unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Local model inference unavailable") from exc


@APP.get("/readyz")
async def readiness_endpoint() -> dict[str, str]:
    """Expose no serving identity: only coarse current/unavailable state."""
    if not production_chat_ready():
        raise HTTPException(status_code=503, detail="unavailable")
    return {"status": "ready"}


@APP.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    return _get_conversation_service().sessions.list_recent()


@APP.get("/sessions/{session_id}")
async def inspect_session(session_id: str) -> dict[str, Any]:
    session = _get_conversation_service().sessions.load(session_id)
    return {k: session[k] for k in ("session_id", "created_at", "latest_activity_at", "title", "revision", "lifecycle_state", "model_identity_digest")}


@APP.get("/boot-feed", response_model=List[BootEvent])
async def boot_feed() -> List[BootEvent]:
    return [BootEvent(**event) for event in boot_history()]


@APP.get("/", response_class=HTMLResponse)
async def root_page() -> HTMLResponse:
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8" />
            <title>SentientOS Chat</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 2rem; background: #111; color: #f5f5f5; }
                #chat { max-width: 640px; margin: 0 auto; }
                #boot-ceremony { margin-bottom: 2rem; padding: 1rem; background: #1b1b1b; border-radius: 8px; }
                #boot-ceremony h2 { margin-top: 0; }
                .boot-entry { margin: 0.5rem 0; padding: 0.5rem; border-left: 4px solid #444; background: #0f0f0f; border-radius: 4px; }
                .boot-entry[data-level="warning"] { border-color: #f0a202; }
                .boot-entry[data-level="error"] { border-color: #f2545b; }
                textarea { width: 100%; min-height: 120px; padding: 0.75rem; font-size: 1rem; }
                button { margin-top: 1rem; padding: 0.75rem 1.5rem; font-size: 1rem; cursor: pointer; }
                .response { margin-top: 2rem; padding: 1rem; background: #1e1e1e; border-radius: 8px; }
            </style>
        </head>
        <body>
            <div id="chat">
                <section id="boot-ceremony">
                    <h2>Boot Ceremony</h2>
                    <div id="boot-feed"></div>
                </section>
                <h1>SentientOS Local Chat</h1>
                <p>Start a local conversation with the SentientOS daemon. All interactions remain on your machine.</p>
                <textarea id="message" placeholder="Type your message..."></textarea>
                <button id="send">Send</button>
                <div id="response" class="response" hidden>
                    <strong>Response:</strong>
                    <p id="response-text"></p>
                </div>
            </div>
            <script>
                async function refreshBootFeed() {
                    try {
                        const res = await fetch('/boot-feed');
                        if (!res.ok) {
                            return;
                        }
                        const data = await res.json();
                        const container = document.getElementById('boot-feed');
                        container.innerHTML = '';
                        data.forEach((event) => {
                            const entry = document.createElement('div');
                            entry.className = 'boot-entry';
                            entry.dataset.level = event.level;
                            const timestamp = new Date(event.timestamp).toLocaleTimeString();
                            entry.innerHTML = `<strong>[${timestamp}]</strong> ${event.message}`;
                            container.appendChild(entry);
                        });
                    } catch (err) {
                        console.warn('Unable to refresh boot feed', err);
                    }
                }

                async function sendMessage() {
                    const messageEl = document.getElementById('message');
                    const responseEl = document.getElementById('response');
                    const responseTextEl = document.getElementById('response-text');
                    const message = messageEl.value.trim();
                    if (!message) {
                        alert('Please enter a message before sending.');
                        return;
                    }
                    const res = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message, session_id: localStorage.getItem('sentientos_session_id') }),
                    });
                    if (!res.ok) {
                        const detail = await res.json().catch(() => ({ detail: 'Unknown error' }));
                        alert(detail.detail || 'Unable to reach SentientOS chat.');
                        return;
                    }
                    const data = await res.json();
                    localStorage.setItem('sentientos_session_id', data.session_id);
                    responseTextEl.textContent = data.response;
                    responseEl.hidden = false;
                }
                document.getElementById('send').addEventListener('click', sendMessage);
                document.getElementById('message').addEventListener('keydown', (event) => {
                    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                        event.preventDefault();
                        sendMessage();
                    }
                });
                refreshBootFeed();
                setInterval(refreshBootFeed, 5000);
            </script>
        </body>
        </html>
        """
    )


def run(host: str = "0.0.0.0", port: int = 5000) -> None:
    import uvicorn

    uvicorn.run(APP, host=host, port=port)
