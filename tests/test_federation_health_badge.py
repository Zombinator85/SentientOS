from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

import sentientos.privilege as privilege


@pytest.fixture
def health_badge(monkeypatch):
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: None)
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: None)
    module = importlib.import_module("federation_health_badge")
    return importlib.reload(module)


def test_compute_health_counts_nested_peers_and_timezone_aware_recent_events(
    health_badge, tmp_path, monkeypatch
):
    log_path = tmp_path / "federation_log.jsonl"
    now = datetime.now(timezone.utc)
    entries = [
        {"timestamp": now.isoformat(), "data": {"peer": "alpha"}},
        {
            "timestamp": (now - timedelta(days=2)).isoformat(),
            "data": {"peer": "beta"},
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n{malformed\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    assert health_badge.compute_health() == {
        "nodes": 2,
        "recent": 1,
        "status": "healthy",
    }


def test_compute_health_reports_missing_log(health_badge, tmp_path, monkeypatch):
    monkeypatch.setattr(health_badge, "LOG_PATH", tmp_path / "missing.jsonl")

    assert health_badge.compute_health() == {
        "nodes": 0,
        "recent": 0,
        "status": "no log",
    }


def test_main_updates_only_requested_health_document(
    health_badge, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    readme = tmp_path / "README.md"
    original_readme = "Federated instances: **preserve this line**\n"
    readme.write_text(original_readme, encoding="utf-8")

    log_path = tmp_path / "federation_log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {"peer": "alpha"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)
    monkeypatch.setattr(
        sys, "argv", ["federation_health_badge.py", "--output", "docs/health.md"]
    )

    health_badge.main()

    assert (tmp_path / "docs/health.md").read_text(encoding="utf-8") == (
        "# Federation Health\n\n- Nodes: 1\n- Recent events: 1\n- Status: healthy\n"
    )
    assert readme.read_text(encoding="utf-8") == original_readme
    assert capsys.readouterr().out.strip() == (
        '{"nodes": 1, "recent": 1, "status": "healthy"}'
    )
