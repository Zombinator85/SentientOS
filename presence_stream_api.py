"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pathlib import Path
import time
from typing import Generator

app = FastAPI(title="Presence Stream API")

def stream_events(path: Path) -> Generator[str, None, None]:
    last_size = 0
    while True:
        if path.exists():
            data = path.read_text()
            if len(data) > last_size:
                new = data[last_size:].splitlines()
                for line in new:
                    yield f"data: {line}\n\n"
                last_size = len(data)
        time.sleep(1)

@app.get("/presence/stream")
def presence_stream() -> StreamingResponse:
    path = Path("logs/presence_stream.jsonl")
    return StreamingResponse(stream_events(path), media_type="text/event-stream")
