from logging_config import get_log_path
import datetime
import json
import os
from pathlib import Path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
OCR_LOG = get_log_path("ocr_relay.jsonl", "OCR_RELAY_LOG")


def generate_html_report(log_file: Path = OCR_LOG) -> str:
    """Return path to generated HTML report from deduplicated OCR log."""
    stats: dict[str, dict[str, object]] = {}
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            msg = data.get("message")
            ts = data.get("timestamp")
            if not msg or ts is None:
                continue
            try:
                dt = (
                    datetime.datetime.utcfromtimestamp(float(ts))
                    if isinstance(ts, (int, float))
                    else datetime.datetime.fromisoformat(str(ts))
                )
            except Exception:
                dt = datetime.datetime.utcnow()
            entry = stats.setdefault(
                msg, {"count": 0, "first": dt, "last": dt}
            )
            entry["count"] = int(entry.get("count", 0)) + int(data.get("count", 1))
            if dt < entry["first"]:
                entry["first"] = dt
            if dt > entry["last"]:
                entry["last"] = dt
    if not stats:
        return ""

    rows = [
        (m, v["count"], v["first"].isoformat(), v["last"].isoformat())
        for m, v in stats.items()
    ]
    rows.sort(key=lambda r: r[1], reverse=True)

    html = [
        "<html><head><meta charset='utf-8'><title>OCR Report</title>",
        "<style>table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:4px}</style>",
        "<script>function sort(n){var t=document.getElementById('tbl');var r=Array.from(t.rows).slice(1);r.sort(function(a,b){return a.cells[n].innerText.localeCompare(b.cells[n].innerText)});r.forEach(function(e){t.appendChild(e)});}</script>",
        "</head><body><table id='tbl'><thead><tr>",
        "<th onclick='sort(0)'>Message</th>",
        "<th onclick='sort(1)'>Count</th>",
        "<th onclick='sort(2)'>First Seen</th>",
        "<th onclick='sort(3)'>Last Seen</th>",
        "</tr></thead><tbody>",
    ]
    for m, c, f, l in rows:
        html.append(
            f"<tr><td>{m}</td><td>{c}</td><td>{f}</td><td>{l}</td></tr>"
        )
    html.append("</tbody></table></body></html>")
    out_name = datetime.datetime.utcnow().strftime("ocr_report_%Y%m%d_%H%M%S.html")
    out_path = log_file.parent / out_name
    out_path.write_text("\n".join(html), encoding="utf-8")
    return str(out_path)


if __name__ == "__main__":  # pragma: no cover - manual usage
    print(generate_html_report())
