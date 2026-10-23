from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from math import isfinite
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterator

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("federation_log.jsonl")

# Federation Health is a bounded local snapshot reader. These limits apply to
# each independent JSONL record; they do not change the log or its writer.
MAX_RECORD_BYTES = 64 * 1024
MAX_JSON_INTEGER_DIGITS = 128


def _bounded_lines(log_file: BinaryIO) -> Iterator[bytes]:
    """Yield complete log records only when they fit the per-record byte bound."""
    while True:
        raw_line = log_file.readline(MAX_RECORD_BYTES + 1)
        if not raw_line:
            return
        if len(raw_line) > MAX_RECORD_BYTES:
            while raw_line and not raw_line.endswith(b"\n"):
                raw_line = log_file.readline(MAX_RECORD_BYTES + 1)
            continue
        yield raw_line


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _parse_bounded_json_integer(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise ValueError("JSON integer exceeds the health snapshot limit")
    return int(token)


def _parse_finite_json_float(token: str) -> float:
    value = float(token)
    if not isfinite(value):
        raise ValueError("JSON float is not finite")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-standard JSON constant: {token}")


def compute_health(hours: int = 24) -> Dict[str, int | str | bool | None]:
    """Return basic federation health stats."""
    if hours <= 0:
        raise ValueError("hours must be positive")
    source = "configured_local_log_snapshot"
    if not LOG_PATH.exists():
        return {
            "nodes": 0,
            "recent": 0,
            "status": "no log",
            "source": source,
            "window_hours": hours,
            "latest_event_at": None,
            "live_telemetry": False,
        }
    now = datetime.now(timezone.utc)
    try:
        cutoff = now - timedelta(hours=hours)
    except OverflowError:
        # A larger positive window includes every representable event timestamp.
        cutoff = datetime.min.replace(tzinfo=timezone.utc)
    nodes = set()
    recent = 0
    latest_event_at: datetime | None = None
    with LOG_PATH.open("rb") as log_file:
        for raw_line in _bounded_lines(log_file):
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                continue
            try:
                entry = json.loads(
                    line,
                    object_pairs_hook=_reject_duplicate_json_keys,
                    parse_int=_parse_bounded_json_integer,
                    parse_float=_parse_finite_json_float,
                    parse_constant=_reject_json_constant,
                )
            except (json.JSONDecodeError, RecursionError, ValueError):
                continue
            if not isinstance(entry, dict):
                continue
            payload = entry.get("data", entry)
            if not isinstance(payload, dict):
                continue
            peer = payload.get("peer")
            if not isinstance(peer, str):
                continue
            peer = peer.strip()
            if not peer or peer.casefold() == "unknown":
                continue
            nodes.add(peer)
            ts = entry.get("timestamp")
            try:
                if isinstance(ts, str) and ts:
                    if ts.endswith("-00:00"):
                        raise ValueError("timestamp UTC offset is unknown")
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if latest_event_at is None or parsed > latest_event_at:
                        latest_event_at = parsed
                    if cutoff <= parsed <= now:
                        recent += 1
            except (TypeError, ValueError):
                continue
    if recent > 0:
        status = "healthy"
    elif latest_event_at is not None and latest_event_at < cutoff:
        status = "stale"
    else:
        status = "quiet"
    latest = (
        latest_event_at.isoformat().replace("+00:00", "Z")
        if latest_event_at is not None
        else None
    )
    return {
        "nodes": len(nodes),
        "recent": recent,
        "status": status,
        "source": source,
        "window_hours": hours,
        "latest_event_at": latest,
        "live_telemetry": False,
    }


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Federation health badge updater")
    ap.add_argument("--hours", type=int, default=24, help="Look back this many hours")
    ap.add_argument("--output", type=Path, default=Path("docs/FEDERATION_HEALTH.md"))
    args = ap.parse_args()
    stats = compute_health(args.hours)
    content = (
        "# Federation Health\n\n"
        f"- Nodes in configured log: {stats['nodes']}\n"
        f"- Events in last {stats['window_hours']} hours: {stats['recent']}\n"
        f"- Latest event in log: {stats['latest_event_at'] or 'none'}\n"
        "- Data source: configured local log snapshot (not live federation telemetry)\n"
        f"- Status: {stats['status']}\n"
    )
    args.output.write_text(content, encoding="utf-8")

    print(json.dumps(stats))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
