from __future__ import annotations

import json
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_goals import resolve_goal
from sentientos.forge_merge_train import ForgeMergeTrain, TrainState
from sentientos.forge_model import ForgeSession
from sentientos.forge_merge_train import TrainEntry
from sentientos.forge_index import rebuild_index


class _Ops:
    def checks_for(self, entry: TrainEntry) -> tuple[str, str | None, str | None]:
        _ = entry
        return ("success", None, None)

    def wait_for_checks(self, entry: TrainEntry, timeout_seconds: int = 1800) -> tuple[str, bool]:
        _ = entry, timeout_seconds
        return ("success", False)

    def is_branch_behind_base(self, entry: TrainEntry, base_branch: str) -> bool:
        _ = entry, base_branch
        return False

    def rebase_branch(self, entry: TrainEntry, base_branch: str):
        _ = entry, base_branch
        raise AssertionError("should not rebase")

    def merge_pull_request(self, entry: TrainEntry, strategy: str):
        _ = entry, strategy
        raise AssertionError("should not merge")


def _entry() -> TrainEntry:
    return TrainEntry(
        run_id="run-1",
        pr_url="https://github.com/o/r/pull/11",
        pr_number=11,
        head_sha="abc",
        branch="forge/1",
        goal_id="forge_smoke_noop",
        campaign_id=None,
        status="ready",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        check_overall="success",
    )


def test_auto_quarantine_activation_on_enforce_receipt_chain(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_RECEIPT_CHAIN_ENFORCE", "1")
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_AUTO", "1")

    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text('{"baseline_integrity_ok":true,"runtime_integrity_ok":true,"baseline_unexpected_change_detected":false}\n', encoding="utf-8")
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_bad.json").write_text('{"schema_version":2,"receipt_id":"bad","created_at":"2026-01-01T00:00:00Z","receipt_hash":"deadbeef","prev_receipt_hash":null}\n', encoding="utf-8")

    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    train.save_state(TrainState(entries=[_entry()]))

    result = train.tick()

    assert result["reason"] == "receipt_chain_broken"
    quarantine = json.loads((tmp_path / "glow/forge/quarantine.json").read_text(encoding="utf-8"))
    assert quarantine["active"] is True
    incidents = sorted((tmp_path / "glow/forge/incidents").glob("incident_*.json"))
    assert incidents


def test_quarantine_blocks_merge_and_publish(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/quarantine.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "active": True,
                "activated_at": "2026-01-01T00:00:00Z",
                "activated_by": "auto",
                "last_incident_id": "x",
                "freeze_forge": True,
                "allow_automerge": False,
                "allow_publish": False,
                "allow_federation_sync": True,
                "notes": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    train.save_state(TrainState(entries=[_entry()]))
    held = train.tick()
    assert held["reason"] == "quarantine_active"

    forge = CathedralForge(repo_root=tmp_path)
    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )
    assert "quarantine_active" in notes
    assert remote["automerge_result"] == "quarantine_active"


def test_quarantine_clear_requires_then_passes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/quarantine.json").write_text('{"schema_version":1,"active":true,"freeze_forge":true,"allow_automerge":false,"allow_publish":false,"allow_federation_sync":true,"notes":[]}\n', encoding="utf-8")

    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_bad.json").write_text('{"schema_version":2,"receipt_id":"bad","created_at":"2026-01-01T00:00:00Z","receipt_hash":"deadbeef","prev_receipt_hash":null}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from scripts import quarantine_clear

    assert quarantine_clear.main([]) == 1

    (tmp_path / "glow/forge/receipts/merge_receipt_bad.json").unlink()
    (tmp_path / "glow/forge/receipts/merge_receipt_ok.json").write_text(
        json.dumps({"schema_version": 2, "receipt_id": "ok", "created_at": "2026-01-01T00:00:00Z", "receipt_hash": "", "prev_receipt_hash": None}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.quarantine_clear.verify_receipt_chain", lambda root: type("R", (), {"ok": True, "to_dict": lambda self: {"status": "ok"}})())
    monkeypatch.setattr("scripts.quarantine_clear.verify_receipt_anchors", lambda root: type("A", (), {"ok": True, "to_dict": lambda self: {"status": "ok"}})())
    monkeypatch.setattr("scripts.quarantine_clear.verify_doctrine_identity", lambda root: (True, {"ok": True}))
    monkeypatch.setattr("scripts.quarantine_clear.federation_integrity_gate", lambda root, context: {"blocked": False, "status": "ok"})

    assert quarantine_clear.main(["--note", "recovered"]) == 0
    payload = json.loads((tmp_path / "glow/forge/quarantine.json").read_text(encoding="utf-8"))
    assert payload["active"] is False


def test_incident_docket_deterministic_shape(tmp_path: Path) -> None:
    from sentientos.integrity_incident import build_incident, write_incident

    incident = build_incident(
        triggers=["federation_integrity_diverged"],
        enforcement_mode="enforce",
        severity="enforced",
        context={"head_sha": "abc"},
        evidence_paths=["glow/forge/receipts/receipts_index.jsonl"],
        suggested_actions=["python scripts/quarantine_status.py"],
        created_at="2026-01-01T00:00:00Z",
    )
    path = write_incident(tmp_path, incident)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["incident_id"].startswith("2026-01-01T00:00:00Z_")
    assert payload["evidence_paths"] == ["glow/forge/receipts/receipts_index.jsonl"]


def test_observability_includes_quarantine_fields(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "glow/forge/quarantine.json").write_text('{"schema_version":1,"active":true,"activated_at":"2026-01-01T00:00:00Z","last_incident_id":"inc-1","freeze_forge":true,"allow_automerge":false,"allow_publish":false,"allow_federation_sync":true,"notes":[]}\n', encoding="utf-8")
    (tmp_path / "glow/forge/incidents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/incidents/incident_2026-01-01T00-00-00Z_abcd.json").write_text('{"incident_id":"inc-1","created_at":"2026-01-01T00:00:00Z","severity":"enforced","triggers":["receipt_chain_broken"]}\n', encoding="utf-8")
    (tmp_path / "pulse").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pulse/integrity_incidents.jsonl").write_text('{"created_at":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")

    payload = rebuild_index(tmp_path)
    assert payload["schema_version"] == 5
    assert payload["quarantine_active"] is True
    assert payload["quarantine_last_incident_id"] == "inc-1"
    assert isinstance(payload["last_incident_summary"], dict)
