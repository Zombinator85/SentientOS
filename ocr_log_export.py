from logging_config import get_log_path
import csv
import datetime
import json
import os
from pathlib import Path


from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
OCR_LOG = get_log_path("ocr_relay.jsonl", "OCR_RELAY_LOG")


def export_last_day_csv(log_file: Path = OCR_LOG) -> str:
    """Export OCR log entries from the last 24h to a CSV file.

    Returns the path to the created file or an empty string if no entries.
    """

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    rows: list[list[str | int]] = []
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            ts = data.get("timestamp")
            if ts is None:
                continue
            try:
                if isinstance(ts, (int, float)):
                    dt = datetime.datetime.utcfromtimestamp(float(ts))
                else:
                    dt = datetime.datetime.fromisoformat(str(ts))
            except Exception:
                continue
            if dt < cutoff:
                continue
            rows.append([dt.isoformat(), data.get("message", ""), data.get("count", 1), data.get("reply", "")])

    if not rows:
        return ""

    out_name = datetime.datetime.utcnow().strftime("ocr_export_%Y%m%d_%H%M%S.csv")
    out_path = log_file.parent / out_name
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "message", "count", "reply"])
        writer.writerows(rows)
    return str(out_path)


def export_last_day_json(log_file: Path = OCR_LOG) -> str:
    """Export deduplicated OCR log from the last 24h as a JSON array."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    stats: dict[str, dict[str, object]] = {}
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            ts = data.get("timestamp")
            msg = data.get("message")
            if ts is None or not msg:
                continue
            try:
                dt = (
                    datetime.datetime.utcfromtimestamp(float(ts))
                    if isinstance(ts, (int, float))
                    else datetime.datetime.fromisoformat(str(ts))
                )
            except Exception:
                continue
            if dt < cutoff:
                continue
            entry = stats.setdefault(msg, {"count": 0, "timestamps": []})
            entry["count"] = int(entry.get("count", 0)) + int(data.get("count", 1))
            entry["timestamps"].append(dt.isoformat())

    if not stats:
        return ""

    out = [
        {"message": m, "count": v["count"], "timestamps": v["timestamps"]}
        for m, v in stats.items()
    ]
    out_name = datetime.datetime.utcnow().strftime("ocr_export_%Y%m%d_%H%M%S.json")
    out_path = log_file.parent / out_name
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return str(out_path)


if __name__ == "__main__":  # pragma: no cover - manual usage
    print(export_last_day_csv())
