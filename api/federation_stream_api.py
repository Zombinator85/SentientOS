"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pathlib import Path
import math
import os
import time
from typing import Callable, Generator, TypeVar, cast

app = FastAPI(title="Federation Stream API")
LOG_PATH = Path("logs/federation_stream.jsonl")
MAX_STREAM_LINE_BYTES = 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
Handler = TypeVar("Handler", bound=Callable[..., object])
typed_get = cast(Callable[[str], Callable[[Handler], Handler]], app.get)


def _read_available_lines(
    path: Path,
    *,
    offset: int,
    file_identity: tuple[int, int] | None,
    pending: bytearray,
    discarding: bool,
    max_line_bytes: int,
) -> tuple[list[str], int, tuple[int, int] | None, bytearray, bool]:
    """Read one bounded append-only log increment, resetting on rotation."""
    try:
        handle = path.open("rb")
    except FileNotFoundError:
        return [], 0, None, bytearray(), False

    with handle:
        metadata = os.fstat(handle.fileno())
        current_identity = (metadata.st_dev, metadata.st_ino)
        if file_identity != current_identity or metadata.st_size < offset:
            offset = 0
            pending = bytearray()
            discarding = False
        handle.seek(offset)
        chunk = handle.read(READ_CHUNK_BYTES)
        offset += len(chunk)

    lines: list[str] = []
    start = 0
    while start < len(chunk):
        newline = chunk.find(b"\n", start)
        end = len(chunk) if newline < 0 else newline
        piece = chunk[start:end]
        if discarding:
            if newline >= 0:
                discarding = False
                pending.clear()
        elif len(pending) + len(piece) > max_line_bytes:
            pending.clear()
            discarding = newline < 0
        else:
            pending.extend(piece)
            if newline >= 0:
                raw_line = bytes(pending)
                if raw_line.endswith(b"\r"):
                    raw_line = raw_line[:-1]
                try:
                    lines.append(raw_line.decode("utf-8"))
                except UnicodeDecodeError:
                    pass
                pending.clear()
        if newline < 0:
            break
        start = newline + 1

    return lines, offset, current_identity, pending, discarding


def stream_events(
    path: Path = LOG_PATH,
    *,
    poll_interval: float = 1.0,
    max_line_bytes: int = MAX_STREAM_LINE_BYTES,
) -> Generator[str, None, None]:
    """Stream complete JSONL records without rereading or buffering full history."""
    if (
        type(poll_interval) not in (int, float)
        or not math.isfinite(poll_interval)
        or poll_interval <= 0
    ):
        raise ValueError("poll_interval must be a finite positive number")
    if type(max_line_bytes) is not int or max_line_bytes <= 0:
        raise ValueError("max_line_bytes must be a positive integer")

    offset = 0
    file_identity: tuple[int, int] | None = None
    pending = bytearray()
    discarding = False
    while True:
        lines, offset, file_identity, pending, discarding = _read_available_lines(
            path,
            offset=offset,
            file_identity=file_identity,
            pending=pending,
            discarding=discarding,
            max_line_bytes=max_line_bytes,
        )
        for line in lines:
            yield f"data: {line}\n\n"
        time.sleep(poll_interval)


@typed_get("/federation/stream")
def federation_stream() -> StreamingResponse:
    require_admin_banner()
    require_lumos_approval()
    return StreamingResponse(stream_events(), media_type="text/event-stream")
