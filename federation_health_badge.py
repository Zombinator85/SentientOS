from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from math import isfinite
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterator

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("federation_log.jsonl")

# Federation Health is a bounded local snapshot reader. These limits do not
# change the log or its writer.
MAX_RECORD_BYTES = 64 * 1024
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_JSON_INTEGER_DIGITS = 128


def _discard_to_line_boundary(log_file: BinaryIO, *, byte_limit: int) -> int:
    """Discard the partial first record in a bounded tail snapshot."""
    discarded = 0
    remaining = byte_limit
    while remaining > 0:
        chunk = log_file.readline(min(MAX_RECORD_BYTES + 1, remaining))
        if not chunk:
            break
        discarded += len(chunk)
        remaining -= len(chunk)
        if chunk.endswith(b"\n"):
            break
    return discarded


def _bounded_lines(log_file: BinaryIO, *, byte_limit: int) -> Iterator[bytes | None]:
    """Yield bounded records; None marks a skipped overlong record."""
    remaining = byte_limit
    while remaining > 0:
        raw_line = log_file.readline(min(MAX_RECORD_BYTES + 1, remaining))
        if not raw_line:
            return
        remaining -= len(raw_line)
        if len(raw_line) > MAX_RECORD_BYTES:
            while raw_line and not raw_line.endswith(b"\n") and remaining > 0:
                raw_line = log_file.readline(min(MAX_RECORD_BYTES + 1, remaining))
                remaining -= len(raw_line)
            yield None
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
            "snapshot_coverage_complete": None,
            "omitted_prefix_bytes": 0,
            "oversized_records_omitted": 0,
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
        file_size = os.fstat(log_file.fileno()).st_size
        scan_start = max(0, file_size - MAX_SNAPSHOT_BYTES)
        omitted_prefix_bytes = scan_start
        if scan_start:
            log_file.seek(scan_start - 1)
            previous_byte = log_file.read(1)
            log_file.seek(scan_start)
            if previous_byte != b"\n":
                discarded = _discard_to_line_boundary(
                    log_file, byte_limit=MAX_SNAPSHOT_BYTES
                )
                omitted_prefix_bytes += discarded
                scan_start += discarded
        bytes_to_read = max(0, file_size - scan_start)
        oversized_records_omitted = 0
        for raw_line in _bounded_lines(log_file, byte_limit=bytes_to_read):
            if raw_line is None:
                oversized_records_omitted += 1
                continue
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
    snapshot_coverage_complete = (
        omitted_prefix_bytes == 0 and oversized_records_omitted == 0
    )
    if not snapshot_coverage_complete:
        status = "partial"
    elif recent > 0:
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
        "snapshot_coverage_complete": snapshot_coverage_complete,
        "omitted_prefix_bytes": omitted_prefix_bytes,
        "oversized_records_omitted": oversized_records_omitted,
    }


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Federation health badge updater")
    ap.add_argument("--hours", type=int, default=24, help="Look back this many hours")
    ap.add_argument("--output", type=Path, default=Path("docs/FEDERATION_HEALTH.md"))
    args = ap.parse_args()
    stats = compute_health(args.hours)
    coverage_complete = stats["snapshot_coverage_complete"]
    if coverage_complete is None:
        coverage = "unavailable (no configured local log)"
    else:
        coverage_status = "complete" if coverage_complete else "partial"
        coverage = (
            f"{coverage_status}; omitted oldest-prefix bytes: "
            f"{stats['omitted_prefix_bytes']}; oversized records skipped: "
            f"{stats['oversized_records_omitted']}"
        )
    content = (
        "# Federation Health\n\n"
        f"- Nodes in configured log: {stats['nodes']}\n"
        f"- Events in last {stats['window_hours']} hours: {stats['recent']}\n"
        f"- Latest event in log: {stats['latest_event_at'] or 'none'}\n"
        f"- Snapshot byte coverage: {coverage}\n"
        "- Data source: configured local log snapshot (not live federation telemetry)\n"
        f"- Status: {stats['status']}\n"
    )
    args.output.write_text(content, encoding="utf-8")

    print(json.dumps(stats))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
