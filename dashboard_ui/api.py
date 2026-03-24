"""FastAPI application for the consolidated operator console."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Iterable, Mapping, Optional, cast

from sentientos.fastapi_stub import (
    Body,
    Depends,
    FastAPI,
    HTMLResponse,
    HTTPException,
    JSONResponse,
    Request,
    Response,
    StaticFiles,
    StreamingResponse,
    Jinja2Templates,
)

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
from sentientos.streams.schema_registry import upgrade_envelope


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
    payload: Mapping[str, object],
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


async def event_source(stream: EventStream) -> AsyncGenerator[str, None]:
    subscriber_id, queue = stream.subscribe()
    try:
        for event in stream.get_recent():
            yield _format_sse(dict(event))
        while True:
            queued_event = await queue.get()
            yield _format_sse(queued_event.as_dict())
    finally:
        stream.unsubscribe(subscriber_id)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _as_string(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _parse_event_payload(payload: Mapping[str, object]) -> tuple[str, str, str, Dict[str, object]]:
    category = _as_string(payload.get("category")).strip()
    if category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid category")
    module = _as_string(payload.get("module")).strip()
    message = _as_string(payload.get("message")).strip()
    if not module or not message:
        raise HTTPException(status_code=422, detail="module and message are required")
    metadata_obj = payload.get("metadata", {})
    metadata = dict(metadata_obj) if isinstance(metadata_obj, Mapping) else {}
    return category, module, message, metadata


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

    state = cast(Any, app.state)
    state.event_stream = event_stream or EventStream(categories=CATEGORIES.keys())

    def get_stream() -> EventStream:
        stream = getattr(state, "event_stream", None)
        if isinstance(stream, EventStream):
            return stream
        replacement = EventStream(categories=CATEGORIES.keys())
        state.event_stream = replacement
        return replacement

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request) -> Response:
        return templates.TemplateResponse("dashboard.html", {"request": request, "categories": CATEGORIES})

    @app.get("/events")
    async def stream_events(stream: object = Depends(get_stream)) -> StreamingResponse:
        stream_obj = stream if isinstance(stream, EventStream) else get_stream()
        return StreamingResponse(event_source(stream_obj), media_type="text/event-stream")

    @app.get("/feed")
    def get_feed(stream: object = Depends(get_stream), limit: int = 50) -> Dict[str, object]:
        stream_obj = stream if isinstance(stream, EventStream) else get_stream()
        return {"events": stream_obj.get_history("feed", limit=limit)}

    @app.get("/oracle")
    def get_oracle(stream: object = Depends(get_stream), limit: int = 50) -> Dict[str, object]:
        stream_obj = stream if isinstance(stream, EventStream) else get_stream()
        return {"events": stream_obj.get_history("oracle", limit=limit)}

    @app.get("/gapseeker")
    def get_gapseeker(stream: object = Depends(get_stream), limit: int = 50) -> Dict[str, object]:
        stream_obj = stream if isinstance(stream, EventStream) else get_stream()
        return {"events": stream_obj.get_history("gapseeker", limit=limit)}

    @app.get("/commits")
    def get_commits(stream: object = Depends(get_stream), limit: int = 50) -> Dict[str, object]:
        stream_obj = stream if isinstance(stream, EventStream) else get_stream()
        return {"events": stream_obj.get_history("commits", limit=limit)}

    @app.get("/research")
    def get_research(stream: object = Depends(get_stream), limit: int = 50) -> Dict[str, object]:
        stream_obj = stream if isinstance(stream, EventStream) else get_stream()
        return {"events": stream_obj.get_history("research", limit=limit)}

    @app.get("/research/archive")
    def download_research_archive(stream: object = Depends(get_stream)) -> JSONResponse:
        stream_obj = stream if isinstance(stream, EventStream) else get_stream()
        return JSONResponse({"reports": stream_obj.get_history("research")})

    @app.post("/events", status_code=201)
    def publish_event(payload: object = Body(...), stream: object = Depends(get_stream)) -> Dict[str, object]:
        category, module, message, metadata = _parse_event_payload(_as_mapping(payload))
        stream_obj = stream if isinstance(stream, EventStream) else get_stream()
        try:
            published = stream_obj.publish(
                category=category,
                message=message,
                module=module,
                metadata=metadata,
            )
        except ValueError as exc:  # pragma: no cover - validated upstream, safety net.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return dict(published.as_dict())

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
        reports = get_recent_drift_reports(limit=limit)
        return [dict(report) for report in reports]

    @app.get("/api/drift/{date_str}")
    def drift_by_date(date_str: str) -> Dict[str, object]:
        try:
            normalized = normalize_drift_date(date_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = get_drift_report_for_date(normalized)
        return dict(payload)

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
        return dict(payload)

    @app.get("/api/pressure/due")
    def pressure_due(as_of: str | None = None, limit: str | None = None) -> Dict[str, object]:
        as_of_time = _parse_iso_timestamp(as_of, "as_of")
        bounded_limit = _parse_limit(limit, _DEFAULT_PRESSURE_LIMIT, _MAX_PRESSURE_LIMIT, "limit")
        due = list_due_pressure_signals(as_of_time)
        return {"signals": [_pressure_response(item) for item in due[:bounded_limit]]}

    @app.post("/api/pressure/{digest}/revalidate")
    def pressure_revalidate(
        digest: str,
        payload: object = Body(...),
    ) -> Dict[str, object]:
        request_payload = _as_mapping(payload)
        actor = _as_string(request_payload.get("actor")).strip()
        if not actor:
            raise HTTPException(status_code=400, detail="actor is required")
        state = get_pressure_signal_state(digest)
        if state is None:
            raise HTTPException(status_code=404, detail="pressure signal not found")
        if state.get("status") in {"closed", "expired"}:
            raise HTTPException(status_code=409, detail="pressure signal is not active")
        as_of_time = _parse_iso_timestamp(_as_string(request_payload.get("as_of")) or None, "as_of")
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
        payload: object = Body(...),
    ) -> Dict[str, object]:
        request_payload = _as_mapping(payload)
        actor = _as_string(request_payload.get("actor")).strip()
        if not actor:
            raise HTTPException(status_code=400, detail="actor is required")
        reason = _as_string(request_payload.get("reason"))
        if reason not in PRESSURE_CLOSURE_REASONS:
            raise HTTPException(status_code=422, detail="invalid closure reason")
        note_value = None
        if request_payload.get("note") is not None:
            note_value = _as_string(request_payload.get("note")).strip()
            if len(note_value) > PRESSURE_CLOSURE_NOTE_LIMIT:
                raise HTTPException(status_code=400, detail="closure note exceeds maximum length")
        state = get_pressure_signal_state(digest)
        if state is None:
            raise HTTPException(status_code=404, detail="pressure signal not found")
        if state.get("status") in {"closed", "expired"}:
            raise HTTPException(status_code=409, detail="pressure signal is already closed")
        closed_at = _parse_iso_timestamp(_as_string(request_payload.get("as_of")) or None, "as_of")
        try:
            event = close_pressure_signal(
                digest,
                actor=actor,
                reason=reason,
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

        async def stream() -> AsyncGenerator[str, None]:
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
                    upgraded = upgrade_envelope(envelope.as_dict())
                    event_id = upgraded.get("event_id")
                    event_type = upgraded.get("event_type")
                    yield _format_sse(
                        upgraded,
                        event_id=_as_string(event_id) if event_id is not None else None,
                        event_type=_as_string(event_type) if event_type is not None else None,
                    )
                for item in adapter.tail(start_cursor, should_stop=lambda: stop):
                    if stop:
                        break
                    if isinstance(item, str):
                        yield item
                        continue
                    if last_replay_id is not None and int(item.event_id) <= last_replay_id:
                        continue
                    upgraded = upgrade_envelope(item.as_dict())
                    event_id = upgraded.get("event_id")
                    event_type = upgraded.get("event_type")
                    yield _format_sse(
                        upgraded,
                        event_id=_as_string(event_id) if event_id is not None else None,
                        event_type=_as_string(event_type) if event_type is not None else None,
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

        async def stream() -> AsyncGenerator[str, None]:
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
                    upgraded = upgrade_envelope(envelope.as_dict())
                    event_id = upgraded.get("event_id")
                    event_type = upgraded.get("event_type")
                    yield _format_sse(
                        upgraded,
                        event_id=_as_string(event_id) if event_id is not None else None,
                        event_type=_as_string(event_type) if event_type is not None else None,
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
                    upgraded = upgrade_envelope(item.as_dict())
                    event_id = upgraded.get("event_id")
                    event_type = upgraded.get("event_type")
                    yield _format_sse(
                        upgraded,
                        event_id=_as_string(event_id) if event_id is not None else None,
                        event_type=_as_string(event_type) if event_type is not None else None,
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
