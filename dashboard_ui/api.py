"""FastAPI application for the consolidated operator console."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .event_stream import EventStream


CATEGORIES: Dict[str, str] = {
    "feed": "Boot Feed",
    "oracle": "OracleCycle Log",
    "gapseeker": "Gap Reports",
    "commits": "CommitWatcher",
    "research": "Deep Research",
}


def _format_sse(payload: Dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def event_source(stream: EventStream):
    subscriber_id, queue = stream.subscribe()
    try:
        for event in stream.get_recent():
            yield _format_sse(event)
        while True:
            event = await queue.get()
            yield _format_sse(event.as_dict())
    finally:
        stream.unsubscribe(subscriber_id)


class EventIn(BaseModel):
    category: str = Field(pattern="^(feed|oracle|gapseeker|commits|research)$")
    module: str
    message: str
    metadata: Dict[str, object] = Field(default_factory=dict)


class ArchiveResponse(BaseModel):
    reports: Iterable[Dict[str, object]]


def create_app(event_stream: Optional[EventStream] = None) -> FastAPI:
    app = FastAPI(title="SentientOS Operator Console")

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.state.event_stream = event_stream or EventStream(categories=CATEGORIES.keys())

    def get_stream() -> EventStream:
        return app.state.event_stream

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request) -> Response:
        return templates.TemplateResponse("dashboard.html", {"request": request, "categories": CATEGORIES})

    @app.get("/events")
    async def stream_events(stream: EventStream = Depends(get_stream)) -> StreamingResponse:
        return StreamingResponse(event_source(stream), media_type="text/event-stream")

    @app.get("/feed")
    def get_feed(stream: EventStream = Depends(get_stream), limit: int = 50):
        return {"events": stream.get_history("feed", limit=limit)}

    @app.get("/oracle")
    def get_oracle(stream: EventStream = Depends(get_stream), limit: int = 50):
        return {"events": stream.get_history("oracle", limit=limit)}

    @app.get("/gapseeker")
    def get_gapseeker(stream: EventStream = Depends(get_stream), limit: int = 50):
        return {"events": stream.get_history("gapseeker", limit=limit)}

    @app.get("/commits")
    def get_commits(stream: EventStream = Depends(get_stream), limit: int = 50):
        return {"events": stream.get_history("commits", limit=limit)}

    @app.get("/research")
    def get_research(stream: EventStream = Depends(get_stream), limit: int = 50):
        return {"events": stream.get_history("research", limit=limit)}

    @app.get("/research/archive")
    def download_research_archive(stream: EventStream = Depends(get_stream)) -> JSONResponse:
        return JSONResponse({"reports": stream.get_history("research")})

    @app.post("/events", status_code=201)
    def publish_event(event: EventIn, stream: EventStream = Depends(get_stream)):
        try:
            published = stream.publish(
                category=event.category,
                message=event.message,
                module=event.module,
                metadata=dict(event.metadata),
            )
        except ValueError as exc:  # pragma: no cover - validated upstream, safety net.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return published.as_dict()

    return app
