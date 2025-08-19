"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pathlib import Path
import time
from typing import Generator

app = FastAPI(title="Federation Stream API")
LOG_PATH = Path("logs/federation_stream.jsonl")

def stream_events(path: Path = LOG_PATH) -> Generator[str, None, None]:
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

@app.get("/federation/stream")
def federation_stream() -> StreamingResponse:
    return StreamingResponse(stream_events(), media_type="text/event-stream")
