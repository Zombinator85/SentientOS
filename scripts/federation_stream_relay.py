"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import json
import math
import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

import requests  # type: ignore[import-untyped]
import yaml

CONFIG_PATH = Path("config/federation.yaml")
LOG_PATH = Path("logs/federation_stream.jsonl")
MAX_EVENT_BYTES = 64 * 1024


def iter_bounded_sse_lines(
    chunks: Iterable[bytes], max_bytes: int = MAX_EVENT_BYTES
) -> Iterator[bytes]:
    """Yield SSE lines while bounding buffering and resynchronizing after oversize."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    buffer = bytearray()
    discarding = False
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise TypeError("stream chunks must be bytes")
        start = 0
        while start < len(chunk):
            newline = chunk.find(b"\n", start)
            end = len(chunk) if newline < 0 else newline
            piece_length = end - start
            if discarding:
                if newline >= 0:
                    discarding = False
                    buffer.clear()
            elif len(buffer) + piece_length > max_bytes:
                buffer.clear()
                discarding = newline < 0
            else:
                buffer.extend(chunk[start:end])
                if newline >= 0:
                    line = bytes(buffer)
                    yield line[:-1] if line.endswith(b"\r") else line
                    buffer.clear()
            if newline < 0:
                break
            start = newline + 1
    if not discarding and buffer:
        line = bytes(buffer)
        yield line[:-1] if line.endswith(b"\r") else line


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject ambiguous duplicate keys at every nesting level."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonfinite_json_constant(value: str) -> object:
    """Reject JavaScript numeric extensions that are not valid JSON."""
    raise ValueError(f"non-finite JSON constant: {value}")


def _parse_finite_json_float(value: str) -> float:
    """Reject exponents that overflow Python's finite JSON number model."""
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON number")
    return parsed


def decode_event_line(line: bytes, source: str) -> dict[str, object] | None:
    """Decode one bounded SSE event object without killing its relay worker."""
    if not isinstance(line, bytes) or len(line) > MAX_EVENT_BYTES:
        return None
    if not line.startswith(b"data:"):
        return None
    try:
        data = json.loads(
            line.split(b":", 1)[1].strip(),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_constant,
            parse_float=_parse_finite_json_float,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    data["source"] = source
    return data


def load_peers(config_path: Path = CONFIG_PATH) -> list[str]:
    """Return valid peer presence URLs from mapping-shaped config rows."""
    if not config_path.exists():
        return []
    try:
        data = yaml.safe_load(config_path.read_text()) or {}
    except Exception:
        return []
    if not isinstance(data, Mapping):
        return []
    peer_rows = data.get("peers")
    if not isinstance(peer_rows, list):
        return []
    urls: list[str] = []
    for peer in peer_rows:
        if not isinstance(peer, Mapping):
            continue
        url = peer.get("url")
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
    return urls

def relay_peer(url: str, log_path: Path = LOG_PATH) -> None:
    """Subscribe to peer presence stream and append events to log."""
    stream_url = url.rstrip("/") + "/stream"
    while True:
        try:
            with requests.get(stream_url, stream=True, timeout=10) as resp:
                resp.raise_for_status()
                for line in iter_bounded_sse_lines(resp.iter_content(chunk_size=8192)):
                    if not line:
                        continue
                    data = decode_event_line(line, url)
                    if data is None:
                        continue
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with log_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(data, allow_nan=False) + "\n")
        except Exception:
            time.sleep(5)

def main() -> None:
    peers = load_peers()
    threads: list[threading.Thread] = []
    for p in peers:
        t = threading.Thread(target=relay_peer, args=(p,), daemon=True)
        t.start()
        threads.append(t)
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
