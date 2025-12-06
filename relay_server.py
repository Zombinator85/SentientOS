"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

import json
import time
from pathlib import Path

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
import http.client
import socket

from fastapi import FastAPI, File, Request, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import DiffLexer
from pydantic import BaseModel

from sentientos.privilege import require_admin_banner, require_lumos_approval
from sentientos.local_model import LocalModel, ModelLoadError

require_admin_banner()
require_lumos_approval()

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "relay.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
LOGGER = logging.getLogger("relay_server")

MODEL: LocalModel | None = None
BACKEND_READY = False


class RelayConfig(BaseModel):
    relay_host: str = "0.0.0.0"
    relay_port: int = int(os.environ.get("RELAY_PORT", 3928))
    llama_host: str = os.environ.get("LLAMA_HOST", "127.0.0.1")
    llama_port: int = int(os.environ.get("LLAMA_PORT", 8080))
    llama_retries: int = int(os.environ.get("LLAMA_RETRIES", 5))
    llama_retry_delay: float = float(os.environ.get("LLAMA_RETRY_DELAY", 1.0))


CONFIG = RelayConfig()


def _ensure_port_available(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            LOGGER.fatal("Port %s is already in use; cannot start relay server", port)
            raise SystemExit(1)


def _check_llama_server() -> bool:
    try:
        conn = http.client.HTTPConnection(CONFIG.llama_host, CONFIG.llama_port, timeout=2)
        conn.request("GET", "/")
        resp = conn.getresponse()
        return resp.status < 500
    except Exception:
        return False


def _wait_for_llama_server() -> bool:
    for attempt in range(1, CONFIG.llama_retries + 1):
        if _check_llama_server():
            LOGGER.info(
                "llama.cpp server is reachable on %s:%s (attempt %s)",
                CONFIG.llama_host,
                CONFIG.llama_port,
                attempt,
            )
            return True
        LOGGER.warning(
            "llama.cpp server not reachable on %s:%s (attempt %s/%s); retrying in %.1fs",
            CONFIG.llama_host,
            CONFIG.llama_port,
            attempt,
            CONFIG.llama_retries,
            CONFIG.llama_retry_delay,
        )
        time.sleep(CONFIG.llama_retry_delay)
    LOGGER.error(
        "llama.cpp server unreachable after %s attempts on %s:%s",
        CONFIG.llama_retries,
        CONFIG.llama_host,
        CONFIG.llama_port,
    )
    return False


def load_model() -> None:
    """Attempt to load the Mistral GGUF backend through LocalModel."""

    global MODEL
    if not _wait_for_llama_server():
        raise RuntimeError("llama.cpp server not reachable")
    try:
        MODEL = LocalModel.autoload()
        LOGGER.info("Local model initialised: %s", MODEL.describe())
    except ModelLoadError as exc:  # pragma: no cover - best effort
        LOGGER.fatal("Local model load failed: %s", exc)
        raise RuntimeError("Local model load failed") from exc
    except Exception as exc:  # pragma: no cover - best effort
        LOGGER.fatal("Unexpected model initialisation failure: %s", exc)
        raise RuntimeError("Unexpected model initialisation failure") from exc


def initialise_backend() -> None:
    global BACKEND_READY

    LOGGER.info(
        "Starting relay backend (llama.cpp at %s:%s)", CONFIG.llama_host, CONFIG.llama_port
    )
    load_model()
    BACKEND_READY = True
    LOGGER.info("Relay backend ready; accepting requests")

LOG_PATH = Path("relay_logs.jsonl")
CODEX_LOG = Path("/daemon/logs/codex.jsonl")
CODEX_PATCH_DIR = Path("/glow/codex_suggestions/")
LEDGER_LOG = Path("/daemon/logs/ledger.jsonl")
CODEX_SESSION_FILE = Path("/daemon/logs/codex_session.json")
app = FastAPI()


@app.on_event("startup")
def on_startup() -> None:
    try:
        initialise_backend()
    except Exception as exc:  # pragma: no cover - startup failure should exit
        LOGGER.error("Relay startup failed: %s", exc)
        raise


class RelayRequest(BaseModel):
    task: str
    context: str = ""


@app.post("/relay")
def relay(req: RelayRequest) -> dict:
    if not BACKEND_READY:
        raise HTTPException(status_code=503, detail="Backend not ready")
    prompt = f"{req.context}\n{req.task}".strip()
    start = time.time()
    if MODEL is not None:
        try:  # pragma: no cover - best effort
            output = MODEL.generate(prompt)
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
    return {"status": "ok", "backend_ready": BACKEND_READY}


@app.get("/health")
def health() -> dict:
    status = "ready" if BACKEND_READY else "starting"
    return {
        "status": status,
        "backend_ready": BACKEND_READY,
        "llama_host": CONFIG.llama_host,
        "llama_port": CONFIG.llama_port,
    }


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


@app.get("/sync/pull/glow")
async def pull_glow(since: float = 0.0) -> dict:
    dest = Path("/glow/archive")
    dest.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(dest.glob("*.txt")):
        mtime = path.stat().st_mtime
        if mtime > since:
            files.append(
                {
                    "name": path.name,
                    "ts": mtime,
                    "content": path.read_text(encoding="utf-8"),
                }
            )
    with open(LOG_PATH, "a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "event": "pull_glow",
                    "files": len(files),
                }
            )
            + "\n"
        )
    return {"files": files}


@app.get("/sync/pull/ledger")
async def pull_ledger(since: str = "") -> dict:
    dest = Path("/daemon/logs/relay_ledger.jsonl")
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if dest.exists():
        for line in dest.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except Exception:  # pragma: no cover - best effort
                continue
            if obj.get("ts", "") > since:
                lines.append(json.dumps(obj))
    with open(LOG_PATH, "a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "event": "pull_ledger",
                    "lines": len(lines),
                }
            )
            + "\n"
        )
    return {"lines": lines}


def _ledger_map() -> dict:
    mapping: dict[str, tuple[int, dict]] = {}
    if LEDGER_LOG.exists():
        for idx, line in enumerate(LEDGER_LOG.read_text(encoding="utf-8").splitlines(), 1):
            try:
                obj = json.loads(line)
            except Exception:  # pragma: no cover - best effort
                continue
            ts = obj.get("ts")
            if ts:
                mapping[ts] = (idx, obj)
    return mapping


@app.get("/codex/status")
def codex_status(limit: int = 5) -> dict:
    ledger_map = _ledger_map()
    repairs: list[dict] = []
    if CODEX_LOG.exists():
        lines = CODEX_LOG.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if len(repairs) >= limit:
                break
            try:
                entry = json.loads(line)
            except Exception:  # pragma: no cover - best effort
                continue
            if not entry.get("codex_patch"):
                continue
            patch_path = Path("/") / entry["codex_patch"]
            diff = ""
            if patch_path.exists():
                diff = patch_path.read_text(encoding="utf-8")
            ts = entry.get("ts", "")
            ledger_link = ""
            ci_passed = entry.get("ci_passed", False)
            if ts in ledger_map:
                line_no, ledger_entry = ledger_map[ts]
                ledger_link = f"ledger.jsonl#{line_no}"
                ci_passed = ledger_entry.get("ci_passed", ci_passed)
            repairs.append(
                {
                    "ts": ts,
                    "iterations": entry.get("iterations", 0),
                    "codex_patch": entry.get("codex_patch", ""),
                    "codex_patch_html": entry.get("codex_patch_html", ""),
                    "patch_id": Path(entry.get("codex_patch", "")).stem,
                    "diff": diff,
                    "ci_passed": ci_passed,
                    "ledger_link": ledger_link,
                }
            )
    return {"repairs": repairs}


@app.get("/codex/session")
def codex_session() -> dict:
    if CODEX_SESSION_FILE.exists():
        try:
            return json.loads(CODEX_SESSION_FILE.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - best effort
            pass
    return {"runs": 0, "iterations": 0, "passes": 0, "failures": 0}


@app.get("/codex/patch/{patch_id}")
def codex_patch(patch_id: str) -> HTMLResponse:
    path_html = CODEX_PATCH_DIR / f"{patch_id}.html"
    if path_html.exists():
        return HTMLResponse(path_html.read_text(encoding="utf-8"))
    path_diff = CODEX_PATCH_DIR / f"{patch_id}.diff"
    if not path_diff.exists():
        raise HTTPException(status_code=404, detail="Patch not found")
    diff = path_diff.read_text(encoding="utf-8")
    html = highlight(diff, DiffLexer(), HtmlFormatter(full=True))
    return HTMLResponse(html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Relay server")
    parser.add_argument("--host", default=CONFIG.relay_host, help="Relay bind host")
    parser.add_argument("--port", type=int, default=CONFIG.relay_port, help="Relay bind port")
    parser.add_argument(
        "--llama-host", default=CONFIG.llama_host, help="llama.cpp host to poll"
    )
    parser.add_argument(
        "--llama-port",
        type=int,
        default=CONFIG.llama_port,
        help="llama.cpp port to poll",
    )
    parser.add_argument(
        "--llama-retries",
        type=int,
        default=CONFIG.llama_retries,
        help="Number of times to poll llama.cpp before failing",
    )
    parser.add_argument(
        "--llama-retry-delay",
        type=float,
        default=CONFIG.llama_retry_delay,
        help="Seconds to wait between llama.cpp polls",
    )
    args = parser.parse_args()

    CONFIG = RelayConfig(
        relay_host=args.host,
        relay_port=args.port,
        llama_host=args.llama_host,
        llama_port=args.llama_port,
        llama_retries=args.llama_retries,
        llama_retry_delay=args.llama_retry_delay,
    )

    _ensure_port_available(CONFIG.relay_port)
    LOGGER.info(
        "Starting relay server on %s:%s (llama.cpp at %s:%s)",
        CONFIG.relay_host,
        CONFIG.relay_port,
        CONFIG.llama_host,
        CONFIG.llama_port,
    )

    try:
        import uvicorn

        uvicorn.run(app, host=CONFIG.relay_host, port=CONFIG.relay_port)
    except Exception as exc:  # pragma: no cover - startup failure should exit
        LOGGER.error("Relay server failed to start: %s", exc)
        raise SystemExit(1) from exc

