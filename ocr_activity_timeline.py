"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
"""Plot timeline of OCR activity over the last 24h."""
import datetime
import json
from pathlib import Path

import matplotlib.pyplot as plt  # type: ignore  # matplotlib optional

from ocr_log_export import OCR_LOG


def plot_timeline(log_file: Path = OCR_LOG) -> Path:
    start = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    hours = [start + datetime.timedelta(hours=i) for i in range(24)]
    new_counts = [0] * 24
    dup_counts = [0] * 24
    seen = set()
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(line)
            except Exception:
                continue
            msg = data.get("message")
            ts = data.get("timestamp")
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
            if dt < start:
                continue
            idx = int((dt - start).total_seconds() // 3600)
            if msg in seen:
                dup_counts[idx] += 1
            else:
                seen.add(msg)
                new_counts[idx] += 1
    plt.figure(figsize=(10, 4))
    h_labels = [h.strftime("%H:%M") for h in hours]
    plt.plot(h_labels, new_counts, label="new")
    plt.plot(h_labels, dup_counts, label="duplicate")
    plt.xticks(rotation=45)
    plt.legend()
    out = log_file.parent / "ocr_timeline.png"
    plt.tight_layout()
    plt.savefig(out)
    return out


if __name__ == "__main__":  # pragma: no cover - manual
    print(plot_timeline())
