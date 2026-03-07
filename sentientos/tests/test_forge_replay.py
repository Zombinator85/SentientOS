from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import forge_replay
from sentientos import artifact_catalog
from sentientos.attestation import write_json


def _seed_repo(root: Path) -> None:
    (root / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (root / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")


def test_replay_never_attempts_git_tag_publish(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append([str(item) for item in argv])
        if len(argv) >= 2 and argv[0] == "git" and argv[1] == "tag":
            raise AssertionError("git tag should not be called in replay mode")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.chdir(tmp_path)

    rc = forge_replay.main(["--verify", "--last-n", "25", "--emit-snapshot", "0"])

    assert rc == 0
    assert not any(len(call) >= 2 and call[0] == "git" and call[1] == "tag" for call in calls)


def test_replay_budget_exhaustion_skip_reason(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_ROLLUP_SIG_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIG_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_INTEGRITY_MAX_VERIFY_STREAMS", "2")

    forge_replay.main(["--verify", "--last-n", "25", "--emit-snapshot", "0"])
    replay_artifacts = sorted((tmp_path / "glow/forge/replay").glob("replay_*.json"), key=lambda item: item.name)
    assert replay_artifacts
    payload = json.loads(replay_artifacts[-1].read_text(encoding="utf-8"))
    assert payload["verification_results"]["snapshot"]["reason"] == "skipped_budget_exhausted"


def test_replay_skips_catalog_rebuild_and_snapshot_without_flags(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    forge_replay.main(["--verify", "--last-n", "5", "--emit-snapshot", "1"])
    replay_artifacts = sorted((tmp_path / "glow/forge/replay").glob("replay_*.json"), key=lambda item: item.name)
    payload = json.loads(replay_artifacts[-1].read_text(encoding="utf-8"))

    assert payload["catalog_rebuild"]["reason"] == "skipped_catalog_rebuild"
    assert payload["snapshot_emit_reason"] == "replay_write_not_permitted"


def test_replay_uses_catalog_resolution_when_present(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    integrity_rel = "glow/forge/integrity/status_2099-01-01T00-00-00Z.json"
    write_json(tmp_path / integrity_rel, {"schema_version": 1, "ts": "2099-01-01T00:00:00Z", "status": "ok", "policy_hash": "p"})
    artifact_catalog.append_catalog_entry(
        tmp_path,
        kind="integrity_status",
        artifact_id="2099-01-01T00:00:00Z",
        relative_path=integrity_rel,
        schema_name="integrity_status",
        schema_version=1,
        links={"policy_hash": "p"},
        summary={"status": "ok"},
        ts="2099-01-01T00:00:00Z",
    )
    monkeypatch.chdir(tmp_path)

    forge_replay.main(["--verify", "--last-n", "5", "--emit-snapshot", "0"])
    replay_artifacts = sorted((tmp_path / "glow/forge/replay").glob("replay_*.json"), key=lambda item: item.name)
    payload = json.loads(replay_artifacts[-1].read_text(encoding="utf-8"))
    assert payload["resolution"]["integrity_status"]["resolution_source"] == "catalog"
