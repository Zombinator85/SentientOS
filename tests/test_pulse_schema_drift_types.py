from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.detect_pulse_schema_drift as schema_drift

pytestmark = pytest.mark.no_legacy_skip


def test_added_event_dicts_sort_by_stream_and_event_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baseline_path = tmp_path / "baseline.json"
    output_path = tmp_path / "report.json"
    baseline_schema: dict[str, object] = {}
    baseline_path.write_text(
        json.dumps(
            {
                "schema": baseline_schema,
                "schema_fingerprint": schema_drift._fingerprint(baseline_schema),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        schema_drift,
        "_extract_schema",
        lambda: {
            "beta": {"events": {"zeta": {"allowed_fields": []}}},
            "alpha": {"events": {"gamma": {"allowed_fields": []}}},
        },
    )

    report = schema_drift.detect_drift(baseline_path=baseline_path, output_path=output_path)

    assert report["added_event_types"] == [
        {"stream": "alpha", "event_type": "gamma"},
        {"stream": "beta", "event_type": "zeta"},
    ]
