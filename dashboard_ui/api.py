"""FastAPI application for the consolidated operator console."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Dict, Iterable, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .event_stream import EventStream
from logging_config import get_log_path
from sentientos.diagnostics.drift_alerts import (
    get_drift_report_for_date,
    get_recent_drift_reports,
    get_silhouette_payload,
    normalize_drift_date,
    SilhouettePayloadError,
)
from sentientos.pressure_queue import (
    PRESSURE_CLOSURE_NOTE_LIMIT,
    PRESSURE_CLOSURE_REASONS,
    close_pressure_signal,
    get_pressure_signal_state,
    list_due_pressure_signals,
    read_pressure_queue,
    revalidate_pressure_signal,
)


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
_STREAM_POLL_INTERVAL = 0.5
_STREAM_HEARTBEAT_SECONDS = 15


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


def _parse_last_event_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _parse_audit_line(raw: bytes) -> dict[str, object] | None:
    try:
        decoded = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    if not decoded:
        return None
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    entry = {"timestamp": timestamp, **data}
    if "prev_hash" in payload:
        entry["prev_hash"] = payload.get("prev_hash")
    if "rolling_hash" in payload:
        entry["rolling_hash"] = payload.get("rolling_hash")
    return entry


def _tail_audit_entries(path: Path, *, max_lines: int) -> list[tuple[int, dict[str, object]]]:
    if max_lines <= 0 or not path.exists():
        return []
    entries: list[tuple[int, dict[str, object]]] = []
    buffer = b""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        while position > 0 and len(entries) < max_lines:
            read_size = min(4096, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            buffer = chunk + buffer
            while b"\n" in buffer and len(entries) < max_lines:
                idx = buffer.rfind(b"\n")
                line = buffer[idx + 1 :]
                buffer = buffer[:idx]
                if not line.strip():
                    continue
                offset = position + idx + 1
                parsed = _parse_audit_line(line)
                if parsed is not None:
                    entries.append((offset, parsed))
        if buffer.strip() and len(entries) < max_lines:
            parsed = _parse_audit_line(buffer)
            if parsed is not None:
                entries.append((position, parsed))
    entries.reverse()
    return entries


async def _follow_audit_entries(
    request: Request,
    path: Path,
    *,
    start_offset: int,
    heartbeat: str,
) -> AsyncIterator[tuple[int, dict[str, object]] | str]:
    offset = max(start_offset, 0)
    last_heartbeat = time.monotonic()
    while True:
        if await request.is_disconnected():
            break
        if not path.exists():
            await asyncio.sleep(_STREAM_POLL_INTERVAL)
            continue
        file_size = path.stat().st_size
        if file_size < offset:
            offset = 0
        emitted = False
        with path.open("rb") as handle:
            handle.seek(offset)
            while True:
                line_start = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                offset = handle.tell()
                parsed = _parse_audit_line(raw)
                if parsed is None:
                    continue
                emitted = True
                yield (line_start, parsed)
        if not emitted and time.monotonic() - last_heartbeat >= _STREAM_HEARTBEAT_SECONDS:
            last_heartbeat = time.monotonic()
            yield _format_sse_comment(heartbeat)
        await asyncio.sleep(_STREAM_POLL_INTERVAL)


def _pressure_stream_payload(entry: dict[str, object], *, event_id: int) -> dict[str, object]:
    payload = {
        "event_id": event_id,
        "event_type": entry.get("event"),
        "signal_id": entry.get("digest"),
        "timestamp": entry.get("timestamp"),
        "payload": {},
    }
    bounded_fields = [
        "signal_type",
        "as_of_date",
        "window_days",
        "severity",
        "counts",
        "source",
        "enqueued_at",
        "created_at",
        "last_reviewed_at",
        "next_review_due_at",
        "status",
        "closure_reason",
        "closure_note",
        "review_count",
        "persistence_count",
        "reviewed_at",
        "closed_at",
        "actor",
    ]
    payload["payload"] = {field: entry.get(field) for field in bounded_fields if field in entry}
    return payload


def _parse_drift_entry_date(entry: dict[str, object]) -> str | None:
    dates = entry.get("dates")
    if isinstance(dates, list):
        for raw in dates:
            if isinstance(raw, str):
                try:
                    return date.fromisoformat(raw).isoformat()
                except ValueError:
                    continue
    timestamp = entry.get("timestamp")
    if isinstance(timestamp, str):
        try:
            return date.fromisoformat(timestamp).isoformat()
        except ValueError:
            try:
                return datetime.fromisoformat(timestamp).date().isoformat()
            except ValueError:
                return None
    return None


_DRIFT_TYPE_FLAGS = {
    "POSTURE_STUCK": "posture_stuck",
    "PLUGIN_DOMINANCE": "plugin_dominance",
    "MOTION_STARVATION": "motion_starvation",
    "ANOMALY_ESCALATION": "anomaly_trend",
}


def _empty_drift_report(date_value: str) -> dict[str, object]:
    return {
        "date": date_value,
        "posture_stuck": False,
        "plugin_dominance": False,
        "motion_starvation": False,
        "anomaly_trend": False,
        "source": "drift_detector",
    }


def _drift_summary_counts(report: dict[str, object]) -> dict[str, int]:
    flags = [flag for flag in _DRIFT_TYPE_FLAGS.values() if report.get(flag)]
    return {"flags_total": len(flags)}


def _drift_stream_payload(report: dict[str, object]) -> dict[str, object]:
    payload = {
        "event_id": report.get("date"),
        "event_type": "drift_report",
        "date": report.get("date"),
        "posture_stuck": report.get("posture_stuck", False),
        "plugin_dominance": report.get("plugin_dominance", False),
        "motion_starvation": report.get("motion_starvation", False),
        "anomaly_trend": report.get("anomaly_trend", False),
        "summary_counts": _drift_summary_counts(report),
    }
    if report.get("source_hash"):
        payload["source_hash"] = report.get("source_hash")
    return payload


def _collect_recent_drift_reports(
    log_path: Path,
    *,
    limit: int,
    since_date: str | None,
) -> list[dict[str, object]]:
    entries = _tail_audit_entries(log_path, max_lines=_MAX_DRIFT_REPLAY_LINES)
    reports: dict[str, dict[str, object]] = {}
    for _, entry in entries:
        if entry.get("type") != "drift_detected":
            continue
        drift_type = entry.get("drift_type")
        flag = _DRIFT_TYPE_FLAGS.get(drift_type)
        if not flag:
            continue
        date_value = _parse_drift_entry_date(entry)
        if date_value is None:
            continue
        report = reports.get(date_value)
        if report is None:
            report = _empty_drift_report(date_value)
            reports[date_value] = report
        report[flag] = True
        source_hash = entry.get("rolling_hash")
        if isinstance(source_hash, str):
            report["source_hash"] = source_hash
    ordered = sorted(reports.values(), key=lambda r: r.get("date", ""), reverse=True)
    if since_date:
        ordered = [report for report in ordered if report.get("date") and report["date"] > since_date]
    return ordered[:limit]


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
        parsed_since_id = _parse_last_event_id(since_id) if since_id is not None else None
        effective_since_id = parsed_since_id if parsed_since_id is not None else header_since_id
        log_path = DEFAULT_PRESSURE_QUEUE_LOG
        replay_entries = _tail_audit_entries(log_path, max_lines=bounded_limit)
        if effective_since_id is not None:
            replay_entries = [
                (offset, entry)
                for offset, entry in replay_entries
                if offset > effective_since_id
            ]
        start_offset = log_path.stat().st_size if log_path.exists() else 0

        async def stream() -> Iterable[str]:
            for offset, entry in replay_entries:
                payload = _pressure_stream_payload(entry, event_id=offset)
                yield _format_sse(payload, event_id=payload["event_id"], event_type="pressure")
            async for item in _follow_audit_entries(
                request,
                log_path,
                start_offset=start_offset,
                heartbeat="pressure-stream-ping",
            ):
                if isinstance(item, str):
                    yield item
                    continue
                offset, entry = item
                payload = _pressure_stream_payload(entry, event_id=offset)
                yield _format_sse(payload, event_id=payload["event_id"], event_type="pressure")

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
        header_since_date = request.headers.get("last-event-id")
        if since_date is None and header_since_date:
            since_date = header_since_date
        normalized_since_date = None
        if since_date is not None:
            try:
                normalized_since_date = normalize_drift_date(since_date)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        log_path = Path(get_log_path("drift_detector.jsonl", "DRIFT_DETECTOR_LOG"))
        replay_reports = _collect_recent_drift_reports(
            log_path,
            limit=bounded_limit,
            since_date=normalized_since_date,
        )
        seen_dates = {report.get("date") for report in replay_reports if report.get("date")}

        async def stream() -> Iterable[str]:
            for report in replay_reports:
                payload = _drift_stream_payload(report)
                yield _format_sse(payload, event_id=payload["event_id"], event_type="drift")
            start_offset = log_path.stat().st_size if log_path.exists() else 0
            async for item in _follow_audit_entries(
                request,
                log_path,
                start_offset=start_offset,
                heartbeat="drift-stream-ping",
            ):
                if isinstance(item, str):
                    yield item
                    continue
                _, entry = item
                if entry.get("type") != "drift_detected":
                    continue
                date_value = _parse_drift_entry_date(entry)
                if date_value is None or date_value in seen_dates:
                    continue
                seen_dates.add(date_value)
                report = _empty_drift_report(date_value)
                drift_type = entry.get("drift_type")
                flag = _DRIFT_TYPE_FLAGS.get(drift_type)
                if flag:
                    report[flag] = True
                source_hash = entry.get("rolling_hash")
                if isinstance(source_hash, str):
                    report["source_hash"] = source_hash
                payload = _drift_stream_payload(report)
                yield _format_sse(payload, event_id=payload["event_id"], event_type="drift")

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)

    return app
