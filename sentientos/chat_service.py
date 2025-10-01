from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .local_model import LocalModel

LOGGER = logging.getLogger(__name__)
APP = FastAPI(title="SentientOS Chat", version="1.0")
_MODEL = LocalModel.autoload()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


@APP.on_event("startup")
async def _startup_event() -> None:
    LOGGER.info("Chat interface ready using %s", _MODEL.describe())


@APP.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty")
    reply = _MODEL.generate(message)
    return ChatResponse(response=reply)


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
                textarea { width: 100%; min-height: 120px; padding: 0.75rem; font-size: 1rem; }
                button { margin-top: 1rem; padding: 0.75rem 1.5rem; font-size: 1rem; cursor: pointer; }
                .response { margin-top: 2rem; padding: 1rem; background: #1e1e1e; border-radius: 8px; }
            </style>
        </head>
        <body>
            <div id="chat">
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
            </script>
        </body>
        </html>
        """
    )


def run(host: str = "0.0.0.0", port: int = 5000) -> None:
    import uvicorn

    uvicorn.run(APP, host=host, port=port)
