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
from sentientos.diagnostics.drift_alerts import (
    get_drift_report_for_date,
    get_recent_drift_reports,
    get_silhouette_payload,
    normalize_drift_date,
    SilhouettePayloadError,
)


CATEGORIES: Dict[str, str] = {
    "feed": "Boot Feed",
    "oracle": "OracleCycle Log",
    "gapseeker": "Gap Reports",
    "commits": "CommitWatcher",
    "research": "Deep Research",
}

_MAX_DRIFT_RANGE = 90


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

    def _coerce_bounded_positive(value: str | None, default: int, name: str) -> int:
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{name} must be a positive integer") from exc
        if parsed <= 0:
            raise HTTPException(status_code=400, detail=f"{name} must be a positive integer")
        return min(parsed, _MAX_DRIFT_RANGE)

    @app.get("/api/drift/recent")
    def drift_recent(n: str | None = None) -> list[Dict[str, object]]:
        limit = _coerce_bounded_positive(n, 7, "n")
        return get_recent_drift_reports(limit=limit)

    @app.get("/api/drift/{date_str}")
    def drift_by_date(date_str: str) -> Dict[str, object]:
        try:
            normalized = normalize_drift_date(date_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return get_drift_report_for_date(normalized)

    @app.get("/api/drift/silhouette/{date_str}")
    def drift_silhouette(date_str: str) -> Dict[str, object]:
        try:
            normalized = normalize_drift_date(date_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            payload = get_silhouette_payload(normalized)
        except SilhouettePayloadError as exc:
            raise HTTPException(status_code=422, detail="invalid silhouette payload") from exc
        if payload is None:
            raise HTTPException(status_code=404, detail="Silhouette not found")
        return payload

    return app
