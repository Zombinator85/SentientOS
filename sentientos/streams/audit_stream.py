"""Audit log tail helpers for event streams."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Iterator


def parse_audit_line(raw: bytes) -> dict[str, object] | None:
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
    entry: dict[str, object] = {"timestamp": timestamp, **data}
    if "prev_hash" in payload:
        entry["prev_hash"] = payload.get("prev_hash")
    if "rolling_hash" in payload:
        entry["rolling_hash"] = payload.get("rolling_hash")
    return entry


def tail_audit_entries(
    path: Path,
    *,
    max_lines: int,
    max_bytes: int | None = None,
) -> list[tuple[int, dict[str, object]]]:
    if max_lines <= 0 or not path.exists():
        return []
    entries: list[tuple[int, dict[str, object]]] = []
    buffer = b""
    bytes_read = 0
    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        while position > 0 and len(entries) < max_lines:
            read_size = min(4096, position)
            if max_bytes is not None and bytes_read + read_size > max_bytes:
                read_size = max_bytes - bytes_read
            if read_size <= 0:
                break
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            bytes_read += len(chunk)
            buffer = chunk + buffer
            while b"\n" in buffer and len(entries) < max_lines:
                idx = buffer.rfind(b"\n")
                line = buffer[idx + 1 :]
                buffer = buffer[:idx]
                if not line.strip():
                    continue
                offset = position + idx + 1
                parsed = parse_audit_line(line)
                if parsed is not None:
                    entries.append((offset, parsed))
        if buffer.strip() and len(entries) < max_lines:
            parsed = parse_audit_line(buffer)
            if parsed is not None:
                entries.append((position, parsed))
    entries.reverse()
    return entries


def follow_audit_entries(
    path: Path,
    *,
    start_offset: int,
    should_stop: Callable[[], bool],
    heartbeat: str,
    poll_interval: float = 0.5,
    heartbeat_seconds: float = 15.0,
    max_bytes_per_poll: int = 262_144,
) -> Iterator[tuple[int, dict[str, object]] | str]:
    offset = max(start_offset, 0)
    last_heartbeat = time.monotonic()
    while True:
        if should_stop():
            break
        if not path.exists():
            time.sleep(poll_interval)
            continue
        file_size = path.stat().st_size
        if file_size < offset:
            offset = 0
        emitted = False
        bytes_read = 0
        with path.open("rb") as handle:
            handle.seek(offset)
            while True:
                if should_stop():
                    return
                line_start = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                bytes_read += len(raw)
                if bytes_read > max_bytes_per_poll:
                    break
                offset = handle.tell()
                parsed = parse_audit_line(raw)
                if parsed is None:
                    continue
                emitted = True
                yield (line_start, parsed)
        if not emitted and time.monotonic() - last_heartbeat >= heartbeat_seconds:
            last_heartbeat = time.monotonic()
            yield f": {heartbeat}\n\n"
        time.sleep(poll_interval)
