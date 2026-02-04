"""FastAPI application for the consolidated operator console."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
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
from sentientos.streams.drift_stream import DriftEventStream
from sentientos.streams.event_stream import ReplayPolicy
from sentientos.pressure_queue import (
    PRESSURE_CLOSURE_NOTE_LIMIT,
    PRESSURE_CLOSURE_REASONS,
    close_pressure_signal,
    get_pressure_signal_state,
    list_due_pressure_signals,
    read_pressure_queue,
    revalidate_pressure_signal,
)
from sentientos.streams.pressure_stream import PressureEventStream


CATEGORIES: Dict[str, str] = {
    "feed": "Boot Feed",
    "oracle": "OracleCycle Log",
    "gapseeker": "Gap Reports",
    "commits": "CommitWatcher",
    "research": "Deep Research",
}

_MAX_DRIFT_RANGE = 90
_MAX_PRESSURE_LIMIT = 200
_DEFAULT_PRESSURE_LIMIT = 50
_MAX_DRIFT_REPLAY_LINES = 2000


def _format_sse(
    payload: Dict[str, object],
    *,
    event_id: str | int | None = None,
    event_type: str | None = None,
) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event_type:
        lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(payload)}")
    return "\n".join(lines) + "\n\n"


def _format_sse_comment(message: str) -> str:
    return f": {message}\n\n"


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


class PressureRevalidateIn(BaseModel):
    as_of: str | None = None
    actor: str


class PressureCloseIn(BaseModel):
    actor: str
    reason: str
    note: str | None = None
    as_of: str | None = None


def _parse_limit(value: str | None, default: int, maximum: int, name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise HTTPException(status_code=400, detail=f"{name} must be a positive integer")
    return min(parsed, maximum)


def _parse_iso_timestamp(value: str | None, name: str) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pressure_response(state: Dict[str, object]) -> Dict[str, object]:
    digest = state.get("digest")
    return {
        "id": digest,
        "digest": digest,
        "signal_type": state.get("signal_type"),
        "severity": state.get("severity"),
        "status": state.get("status"),
        "created_at": state.get("created_at"),
        "last_reviewed_at": state.get("last_reviewed_at"),
        "next_review_due_at": state.get("next_review_due_at"),
        "counts": state.get("counts", {}),
        "as_of_date": state.get("as_of_date"),
        "window_days": state.get("window_days"),
        "source": state.get("source"),
        "review_count": state.get("review_count"),
        "persistence_count": state.get("persistence_count"),
    }


def _parse_last_event_id(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


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

    @app.get("/api/pressure/due")
    def pressure_due(as_of: str | None = None, limit: str | None = None) -> Dict[str, object]:
        as_of_time = _parse_iso_timestamp(as_of, "as_of")
        bounded_limit = _parse_limit(limit, _DEFAULT_PRESSURE_LIMIT, _MAX_PRESSURE_LIMIT, "limit")
        due = list_due_pressure_signals(as_of_time)
        return {"signals": [_pressure_response(item) for item in due[:bounded_limit]]}

    @app.post("/api/pressure/{digest}/revalidate")
    def pressure_revalidate(
        digest: str,
        payload: PressureRevalidateIn = Body(...),
    ) -> Dict[str, object]:
        actor = payload.actor.strip() if isinstance(payload.actor, str) else ""
        if not actor:
            raise HTTPException(status_code=400, detail="actor is required")
        state = get_pressure_signal_state(digest)
        if state is None:
            raise HTTPException(status_code=404, detail="pressure signal not found")
        if state.get("status") in {"closed", "expired"}:
            raise HTTPException(status_code=409, detail="pressure signal is not active")
        as_of_time = _parse_iso_timestamp(payload.as_of, "as_of")
        try:
            event = revalidate_pressure_signal(digest, as_of_time=as_of_time, actor=actor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        updated = get_pressure_signal_state(digest) or state
        return {
            "signal": _pressure_response(updated),
            "event": {"id": event.get("digest"), "digest": event.get("digest"), "event": event.get("event")},
        }

    @app.post("/api/pressure/{digest}/close")
    def pressure_close(
        digest: str,
        payload: PressureCloseIn = Body(...),
    ) -> Dict[str, object]:
        actor = payload.actor.strip() if isinstance(payload.actor, str) else ""
        if not actor:
            raise HTTPException(status_code=400, detail="actor is required")
        if payload.reason not in PRESSURE_CLOSURE_REASONS:
            raise HTTPException(status_code=422, detail="invalid closure reason")
        note_value = None
        if payload.note is not None:
            note_value = str(payload.note).strip()
            if len(note_value) > PRESSURE_CLOSURE_NOTE_LIMIT:
                raise HTTPException(status_code=400, detail="closure note exceeds maximum length")
        state = get_pressure_signal_state(digest)
        if state is None:
            raise HTTPException(status_code=404, detail="pressure signal not found")
        if state.get("status") in {"closed", "expired"}:
            raise HTTPException(status_code=409, detail="pressure signal is already closed")
        closed_at = _parse_iso_timestamp(payload.as_of, "as_of")
        try:
            event = close_pressure_signal(
                digest,
                actor=actor,
                reason=payload.reason,
                note=note_value,
                closed_at=closed_at,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        updated = get_pressure_signal_state(digest) or state
        return {
            "signal": _pressure_response(updated),
            "event": {"id": event.get("digest"), "digest": event.get("digest"), "event": event.get("event")},
        }

    @app.get("/api/pressure/recent")
    def pressure_recent(limit: str | None = None) -> Dict[str, object]:
        bounded_limit = _parse_limit(limit, _DEFAULT_PRESSURE_LIMIT, _MAX_PRESSURE_LIMIT, "limit")
        entries = read_pressure_queue()
        recent = list(reversed(entries[-bounded_limit:])) if entries else []
        return {"events": recent}

    @app.get("/api/pressure/stream")
    async def pressure_stream(
        request: Request,
        since_id: str | None = None,
        limit: str | None = None,
    ) -> StreamingResponse:
        bounded_limit = _parse_limit(limit, _DEFAULT_PRESSURE_LIMIT, _MAX_PRESSURE_LIMIT, "limit")
        header_since_id = _parse_last_event_id(request.headers.get("last-event-id"))
        query_since_id = _parse_last_event_id(since_id)
        effective_since_id = header_since_id or query_since_id
        adapter = PressureEventStream(
            replay_policy=ReplayPolicy(max_replay_items=_MAX_PRESSURE_LIMIT, max_replay_bytes=512_000),
        )
        replay = adapter.replay(effective_since_id, bounded_limit)
        last_replay_id = int(replay[-1].event_id) if replay else None
        start_cursor = (
            str(last_replay_id)
            if last_replay_id is not None
            else str(adapter.log_path.stat().st_size if adapter.log_path.exists() else 0)
        )

        async def stream() -> Iterable[str]:
            stop = False

            async def monitor_disconnect() -> None:
                nonlocal stop
                while not stop:
                    if await request.is_disconnected():
                        stop = True
                        break
                    await asyncio.sleep(0.1)

            monitor = asyncio.create_task(monitor_disconnect())
            try:
                for envelope in replay:
                    yield _format_sse(
                        envelope.as_dict(),
                        event_id=envelope.event_id,
                        event_type=envelope.event_type,
                    )
                for item in adapter.tail(start_cursor, should_stop=lambda: stop):
                    if stop:
                        break
                    if isinstance(item, str):
                        yield item
                        continue
                    if last_replay_id is not None and int(item.event_id) <= last_replay_id:
                        continue
                    yield _format_sse(
                        item.as_dict(),
                        event_id=item.event_id,
                        event_type=item.event_type,
                    )
            finally:
                stop = True
                monitor.cancel()

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)

    @app.get("/api/drift/stream")
    async def drift_stream(
        request: Request,
        since_date: str | None = None,
        limit: str | None = None,
    ) -> StreamingResponse:
        bounded_limit = _parse_limit(limit, 7, _MAX_DRIFT_RANGE, "limit")
        header_since_date = _parse_last_event_id(request.headers.get("last-event-id"))
        query_since_date = _parse_last_event_id(since_date)
        effective_since_date = header_since_date or query_since_date
        normalized_since_date = None
        if effective_since_date is not None:
            try:
                normalized_since_date = normalize_drift_date(effective_since_date)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        adapter = DriftEventStream(
            replay_policy=ReplayPolicy(max_replay_items=_MAX_DRIFT_RANGE, max_replay_bytes=512_000),
            max_replay_lines=_MAX_DRIFT_REPLAY_LINES,
        )
        replay = adapter.replay(normalized_since_date, bounded_limit)
        seen_ids = {envelope.event_id for envelope in replay}

        async def stream() -> Iterable[str]:
            stop = False

            async def monitor_disconnect() -> None:
                nonlocal stop
                while not stop:
                    if await request.is_disconnected():
                        stop = True
                        break
                    await asyncio.sleep(0.1)

            monitor = asyncio.create_task(monitor_disconnect())
            try:
                for envelope in replay:
                    yield _format_sse(
                        envelope.as_dict(),
                        event_id=envelope.event_id,
                        event_type=envelope.event_type,
                    )
                for item in adapter.tail(normalized_since_date, should_stop=lambda: stop):
                    if stop:
                        break
                    if isinstance(item, str):
                        yield item
                        continue
                    if item.event_id in seen_ids:
                        continue
                    seen_ids.add(item.event_id)
                    yield _format_sse(
                        item.as_dict(),
                        event_id=item.event_id,
                        event_type=item.event_type,
                    )
            finally:
                stop = True
                monitor.cancel()

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)

    return app
