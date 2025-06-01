import csv
import datetime
import json
import os
from pathlib import Path


OCR_LOG = Path(os.getenv("OCR_RELAY_LOG", "logs/ocr_relay.jsonl"))


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


if __name__ == "__main__":  # pragma: no cover - manual usage
    print(export_last_day_csv())

