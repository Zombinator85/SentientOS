from __future__ import annotations

from pathlib import Path

from sentientos import github_artifacts
from sentientos.github_artifacts import ArtifactRef, parse_bundle


def test_parse_bundle_tolerates_missing_files(tmp_path: Path) -> None:
    bundle = parse_bundle(tmp_path)

    assert bundle.source == "remote"
    assert "bundle_missing_required:stability_doctrine.json" in bundle.errors
    assert "bundle_missing_required:contract_status.json" in bundle.errors
    assert "bundle_missing_required:artifact_metadata.json" in bundle.errors


def test_parse_bundle_tolerates_corrupt_json(tmp_path: Path) -> None:
    (tmp_path / "contract_status.json").write_text("{oops", encoding="utf-8")
    (tmp_path / "stability_doctrine.json").write_text('{"baseline_integrity_ok": true}', encoding="utf-8")
    (tmp_path / "ci_baseline.json").write_text('{"failed_count": 0}', encoding="utf-8")
    (tmp_path / "artifact_metadata.json").write_text('{"sha": "abc"}', encoding="utf-8")

    bundle = parse_bundle(tmp_path)

    assert "invalid_json:contract_status.json" in bundle.errors
    assert "stability_doctrine.json" in bundle.parsed


def test_find_contract_artifact_paginates_and_selects_from_later_page(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr("sentientos.github_artifacts._capabilities", lambda: {"gh": False, "token": True})

    def fake_http_pages(url: str, token: str) -> list[dict[str, object]]:
        assert token == "t"
        if "/actions/runs" in url and "/artifacts" not in url:
            return [{"workflow_runs": [{"id": 18, "head_sha": "abc", "pull_requests": [{"number": 7}]}]}]
        if "/actions/runs/18/artifacts" in url:
            return [
                {"artifacts": [{"name": "other", "workflow_run": {"id": 18, "head_sha": "abc"}, "created_at": "2026-01-01T00:00:00Z"}]},
                {
                    "artifacts": [
                        {
                            "name": "sentientos-contracts-abc",
                            "workflow_run": {"id": 18, "head_sha": "abc", "pull_requests": [{"number": 7}]},
                            "archive_download_url": "https://example.invalid/a.zip",
                            "created_at": "2026-01-01T00:01:00Z",
                        }
                    ]
                },
            ]
        return []

    monkeypatch.setattr("sentientos.github_artifacts._http_json_pages", fake_http_pages)

    ref = github_artifacts.find_contract_artifact_for_sha(7, "abc")

    assert ref is not None
    assert ref.run_id == 18
    assert ref.selected_via == "api:run-artifacts"


def test_find_contract_artifact_chooses_newest_match(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr("sentientos.github_artifacts._capabilities", lambda: {"gh": False, "token": True})

    def fake_http_pages(url: str, token: str) -> list[dict[str, object]]:
        if "/actions/runs" in url and "/artifacts" not in url:
            return [{"workflow_runs": [{"id": 90, "head_sha": "abc", "pull_requests": [{"number": 7}]}]}]
        if "/actions/runs/90/artifacts" in url:
            return [
                {
                    "artifacts": [
                        {
                            "name": "sentientos-contracts-abc",
                            "workflow_run": {"id": 90, "head_sha": "abc", "pull_requests": [{"number": 7}]},
                            "archive_download_url": "https://example.invalid/old.zip",
                            "created_at": "2026-01-01T00:00:00Z",
                        },
                        {
                            "name": "sentientos-contracts-abc",
                            "workflow_run": {"id": 90, "head_sha": "abc", "pull_requests": [{"number": 7}]},
                            "archive_download_url": "https://example.invalid/new.zip",
                            "created_at": "2026-01-01T00:02:00Z",
                        },
                    ]
                }
            ]
        return []

    monkeypatch.setattr("sentientos.github_artifacts._http_json_pages", fake_http_pages)

    ref = github_artifacts.find_contract_artifact_for_sha(7, "abc")

    assert isinstance(ref, ArtifactRef)
    assert ref.url.endswith("new.zip")
    assert ref.created_at == "2026-01-01T00:02:00Z"
