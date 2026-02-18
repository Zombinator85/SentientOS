from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_provenance import ForgeProvenance, append_chain, validate_chain
from sentientos.forge_replay import replay_provenance


def test_bundle_writes_blobs_and_digests(tmp_path: Path) -> None:
    prov = ForgeProvenance(tmp_path, run_id="run-1")
    step = prov.make_step(
        step_id="s1",
        kind="tests",
        command={"argv": ["python", "-V"]},
        cwd=str(tmp_path),
        env_fingerprint="env",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        exit_code=0,
        stdout="hello stdout",
        stderr="hello stderr",
        artifacts_written=[],
    )
    prov.add_step(step, stdout="hello stdout", stderr="hello stderr")
    header = prov.build_header(
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        initiator="manual",
        request_id=None,
        goal="forge_smoke_noop",
        goal_id="forge_smoke_noop",
        campaign_id=None,
        transaction_status="aborted",
        quarantine_ref=None,
    )
    out_path, bundle, _chain = prov.finalize(header=header, env_cache_key="abc", before_snapshot=None, after_snapshot=None, artifacts=[])
    assert out_path.name == "prov_run-1.json"
    assert bundle.steps[0].stdout_digest
    blob_files = list((tmp_path / "glow/forge/provenance/blobs").glob("*.txt"))
    assert blob_files


def test_chain_validate_detects_tamper(tmp_path: Path) -> None:
    append_chain(tmp_path, run_id="r1", bundle_sha256="a")
    append_chain(tmp_path, run_id="r2", bundle_sha256="b")
    ok = validate_chain(tmp_path)
    assert ok["valid"] is True

    chain_path = tmp_path / "glow/forge/provenance/chain.jsonl"
    rows = chain_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(rows[1])
    second["prev_sha256"] = "tampered"
    rows[1] = json.dumps(second, sort_keys=True)
    chain_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    bad = validate_chain(tmp_path)
    assert bad["valid"] is False


def test_forge_smoke_emits_provenance(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts/contract_drift.py").write_text("", encoding="utf-8")
    (tmp_path / "scripts/emit_contract_status.py").write_text("", encoding="utf-8")
    (tmp_path / "glow/contracts/contract_status.json").write_text("{}\n", encoding="utf-8")

    forge = CathedralForge(repo_root=tmp_path)

    def fake_step(*args, **kwargs):  # type: ignore[no-untyped-def]
        from sentientos.forge_model import CommandResult

        cmd = kwargs.get("command") or args[0]
        return CommandResult(step=cmd.step, argv=cmd.argv, cwd=str(tmp_path), env_overlay={}, timeout_seconds=10, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(forge, "_run_step", fake_step)
    from sentientos.forge_model import ForgeSession

    monkeypatch.setattr(
        forge,
        "_create_session",
        lambda generated_at: ForgeSession(
            session_id="sid",
            root_path=str(tmp_path),
            strategy="copy",
            branch_name="forge/sid",
            env_cache_key="cache-1",
        ),
    )
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda path: type("E", (), {"python": "python", "venv_path": "venv", "created": False, "install_summary": "ok", "cache_key": "cache-1"})())
    monkeypatch.setattr(forge, "_cleanup_session", lambda session: None)

    report = forge.run("forge_smoke_noop")
    assert report.provenance_run_id
    assert report.provenance_path


def test_replay_dry_run_writes_step_list(tmp_path: Path) -> None:
    bundle = {
        "header": {
            "schema_version": 1,
            "run_id": "rid",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "initiator": "manual",
            "request_id": None,
            "goal": "forge_smoke_noop",
            "goal_id": "forge_smoke_noop",
            "campaign_id": None,
            "transaction_status": "aborted",
            "quarantine_ref": None,
        },
        "repo_root_fingerprint": "x",
        "env_cache_key": "k",
        "python_version": "3.11",
        "dependency_fingerprint": "dep",
        "before_snapshot_digest": None,
        "after_snapshot_digest": None,
        "steps": [
            {
                "step_id": "tests",
                "kind": "tests",
                "command": {"argv": ["python", "-V"]},
                "cwd": str(tmp_path),
                "env_fingerprint": "env",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "exit_code": 0,
                "stdout_digest": "",
                "stderr_digest": "",
                "artifacts_written": [],
                "notes": "",
            }
        ],
        "final_artifact_index": [],
    }
    prov_path = tmp_path / "glow/forge/provenance/prov_rid.json"
    prov_path.parent.mkdir(parents=True, exist_ok=True)
    prov_path.write_text(json.dumps(bundle) + "\n", encoding="utf-8")

    out = replay_provenance(str(prov_path), repo_root=tmp_path, dry_run=True)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    assert payload["steps"]


def test_replay_exec_records_divergence(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    bundle = {
        "header": {
            "schema_version": 1,
            "run_id": "rid2",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "initiator": "manual",
            "request_id": None,
            "goal": "forge_smoke_noop",
            "goal_id": "forge_smoke_noop",
            "campaign_id": None,
            "transaction_status": "aborted",
            "quarantine_ref": None,
        },
        "repo_root_fingerprint": "x",
        "env_cache_key": "expected",
        "python_version": "3.11",
        "dependency_fingerprint": "dep",
        "before_snapshot_digest": None,
        "after_snapshot_digest": None,
        "steps": [
            {
                "step_id": "tests",
                "kind": "tests",
                "command": {"argv": ["python", "-V"]},
                "cwd": str(tmp_path),
                "env_fingerprint": "env",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "exit_code": 0,
                "stdout_digest": "deadbeef",
                "stderr_digest": "deadbeef",
                "artifacts_written": [],
                "notes": "",
            }
        ],
        "final_artifact_index": [],
    }
    prov_path = tmp_path / "glow/forge/provenance/prov_rid2.json"
    prov_path.parent.mkdir(parents=True, exist_ok=True)
    prov_path.write_text(json.dumps(bundle) + "\n", encoding="utf-8")

    monkeypatch.setattr("sentientos.forge_replay.bootstrap_env", lambda path: type("E", (), {"cache_key": "actual"})())

    out = replay_provenance(str(prov_path), repo_root=tmp_path, dry_run=False)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["matched_env_cache_key"] is False
    assert payload["steps"][0]["executed"] is True
    assert payload["steps"][0]["matched_stdout"] is False
