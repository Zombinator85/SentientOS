"""Incident reporter bundling camera and audio evidence."""
from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from logging_config import get_log_path
from perception_journal import PerceptionJournal


@dataclass
class IncidentSummary:
    event_id: str
    start: datetime
    end: datetime
    clip_path: Path
    peak_score: float
    note: str = ""


class IncidentReporter:
    """Build local HTML bundles summarizing perception incidents."""

    def __init__(self, output_dir: Path | None = None, journal: PerceptionJournal | None = None) -> None:
        self.output_dir = output_dir or (get_log_path("reports") / "incidents")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.journal = journal or PerceptionJournal()

    def build_bundle(
        self,
        incident: IncidentSummary,
        loudness_events: Sequence[dict[str, object]],
        attachments: Iterable[Path] | None = None,
    ) -> Path:
        bundle_dir = self.output_dir / incident.event_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        clip_target = bundle_dir / incident.clip_path.name
        shutil.copy2(incident.clip_path, clip_target)
        metadata = {
            "event_id": incident.event_id,
            "start": incident.start.isoformat(),
            "end": incident.end.isoformat(),
            "duration_seconds": round((incident.end - incident.start).total_seconds(), 2),
            "peak_motion_score": round(incident.peak_score, 4),
            "note": incident.note,
            "clip": clip_target.name,
            "audio_events": loudness_events,
        }
        (bundle_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        html = self._render_html(metadata)
        (bundle_dir / "index.html").write_text(html, encoding="utf-8")
        if attachments:
            for extra in attachments:
                if extra.exists():
                    shutil.copy2(extra, bundle_dir / extra.name)
        zip_path = self.output_dir / f"{incident.event_id}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in bundle_dir.iterdir():
                archive.write(item, arcname=item.name)
        self.journal.record(
            ["incident_bundle", "vision"],
            "Camera incident bundle generated",
            {
                "event_id": incident.event_id,
                "clip": clip_target.name,
                "zip": zip_path.name,
                "audio_events": len(loudness_events),
            },
        )
        return zip_path

    def _render_html(self, metadata: dict[str, object]) -> str:
        audio_rows = "".join(
            f"<tr><td>{idx + 1}</td><td>{ev.get('start')}</td><td>{ev.get('end')}</td><td>{ev.get('peak_db')}</td><td>{ev.get('average_db')}</td></tr>"
            for idx, ev in enumerate(metadata.get("audio_events", []))
        )
        if not audio_rows:
            audio_rows = "<tr><td colspan='5'>No loudness events recorded</td></tr>"
        html = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<title>SentientOS Incident {metadata.get('event_id')}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
th {{ background-color: #f2f2f2; }}
section {{ margin-bottom: 1.5rem; }}
</style>
</head>
<body>
<h1>Incident {metadata.get('event_id')}</h1>
<section>
  <p><strong>Start:</strong> {metadata.get('start')}</p>
  <p><strong>End:</strong> {metadata.get('end')}</p>
  <p><strong>Duration:</strong> {metadata.get('duration_seconds')} seconds</p>
  <p><strong>Peak motion score:</strong> {metadata.get('peak_motion_score')}</p>
  <p><strong>Note:</strong> {metadata.get('note') or 'N/A'}</p>
  <p><a href="{metadata.get('clip')}">Download clip</a></p>
</section>
<section>
  <h2>Loudness events</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Start</th><th>End</th><th>Peak dB</th><th>Average dB</th></tr>
    </thead>
    <tbody>
      {audio_rows}
    </tbody>
  </table>
</section>
</body>
</html>
"""
        return html.strip()


__all__ = ["IncidentReporter", "IncidentSummary"]
