from datetime import datetime
from reporter import IncidentReporter, IncidentSummary


def test_incident_reporter_builds_bundle(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake data")
    reporter = IncidentReporter(output_dir=tmp_path / "bundles")
    incident = IncidentSummary(
        event_id="evt1",
        start=datetime(2024, 1, 1, 0, 0, 0),
        end=datetime(2024, 1, 1, 0, 0, 5),
        clip_path=clip,
        peak_score=0.42,
        note="Vehicle detected",
    )
    loudness = [
        {
            "start": "2024-01-01T00:00:01",
            "end": "2024-01-01T00:00:04",
            "peak_db": 82.5,
            "average_db": 76.1,
            "duration": 3.0,
            "tags": ["noisy"],
        }
    ]
    bundle = reporter.build_bundle(incident, loudness)
    assert bundle.exists()
    metadata = (tmp_path / "bundles" / "evt1" / "metadata.json").read_text(encoding="utf-8")
    assert "Vehicle detected" in metadata
    html = (tmp_path / "bundles" / "evt1" / "index.html").read_text(encoding="utf-8")
    assert "Vehicle detected" in html
