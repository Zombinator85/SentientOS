from __future__ import annotations

import logging
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .change_narrator import build_default_change_narrator
from .event_stream import history as boot_history
from .local_model import LocalModel

LOGGER = logging.getLogger(__name__)
APP = FastAPI(title="SentientOS Chat", version="1.0")
_MODEL = LocalModel.autoload()
try:
    _CHANGE_NARRATOR = build_default_change_narrator()
except Exception:  # pragma: no cover - defensive initialization
    LOGGER.exception("Unable to initialise change narrator")
    _CHANGE_NARRATOR = None


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


class BootEvent(BaseModel):
    timestamp: str
    message: str
    level: str


@APP.on_event("startup")
async def _startup_event() -> None:
    LOGGER.info("Chat interface ready using %s", _MODEL.describe())


@APP.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty")
    if _CHANGE_NARRATOR is not None:
        summary = _CHANGE_NARRATOR.maybe_respond(message)
        if summary is not None:
            return ChatResponse(response=summary)
    reply = _MODEL.generate(message)
    return ChatResponse(response=reply)


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
                        body: JSON.stringify({ message }),
                    });
                    if (!res.ok) {
                        const detail = await res.json().catch(() => ({ detail: 'Unknown error' }));
                        alert(detail.detail || 'Unable to reach SentientOS chat.');
                        return;
                    }
                    const data = await res.json();
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
