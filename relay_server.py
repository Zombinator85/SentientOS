"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

import json
import time
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from pydantic import BaseModel

require_admin_banner()
require_lumos_approval()

MODEL = None
MODEL_PATHS = {
    "120b": Path("/models/gpt-oss-120b-quantized"),
    "20b": Path("/models/gpt-oss-20b"),
}


def load_model() -> None:
    """Attempt to load a GPT-OSS model for local inference."""
    global MODEL
    try:
        from transformers import pipeline
    except Exception:  # pragma: no cover - best effort
        MODEL = None
        return
    for size in ["120b", "20b"]:
        path = MODEL_PATHS.get(size)
        try:
            MODEL = pipeline("text-generation", model=str(path))
            print(f"GPT-OSS {size} model loaded")
            return
        except Exception as exc:  # pragma: no cover - best effort
            print(f"Model {size} load failed: {exc}")
    MODEL = None


load_model()

LOG_PATH = Path("relay_logs.jsonl")
app = FastAPI()


class RelayRequest(BaseModel):
    task: str
    context: str = ""


@app.post("/relay")
def relay(req: RelayRequest) -> dict:
    prompt = f"{req.context}\n{req.task}".strip()
    start = time.time()
    if MODEL is not None:
        try:  # pragma: no cover - best effort
            result = MODEL(prompt, max_new_tokens=50)
            output = result[0]["generated_text"]
        except Exception:  # pragma: no cover - best effort
            output = f"Echo: {req.task}"
    else:
        output = f"Echo: {req.task}"
    latency_ms = (time.time() - start) * 1000
    response = {"output": output, "latency_ms": latency_ms}
    with open(LOG_PATH, "a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "request": req.dict(),
                    "response": response,
                }
            )
            + "\n"
        )
    return response


@app.get("/ping")
def ping() -> dict:
    return {"status": "ok"}


@app.post("/sync/glow")
async def sync_glow(file: UploadFile = File(...)) -> dict:
    dest = Path("/glow/archive")
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / Path(file.filename).name
    content = await file.read()
    if target.exists():
        try:
            with open(target, "a", encoding="utf-8") as f:
                f.write("\n" + content.decode("utf-8"))
        except Exception:  # pragma: no cover - best effort
            with open(target, "ab") as f:
                f.write(b"\n" + content)
    else:
        target.write_bytes(content)
    with open(LOG_PATH, "a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "event": "sync_glow",
                    "file": file.filename,
                }
            )
            + "\n"
        )
    return {"status": "ok"}


@app.post("/sync/ledger")
async def sync_ledger(request: Request) -> dict:
    dest = Path("/daemon/logs/relay_ledger.jsonl")
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = await request.body()
    text = body.decode("utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    with open(dest, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    with open(LOG_PATH, "a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "event": "sync_ledger",
                    "lines": len(lines),
                }
            )
            + "\n"
        )
    return {"status": "ok", "lines": len(lines)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)

