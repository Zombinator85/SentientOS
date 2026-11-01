from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos import artifact_catalog
from sentientos.integrity_incident import build_incident, write_incident
from sentientos.remediation_pack import emit_pack_from_trace
from scripts import quarantine_clear


def test_catalog_append_and_latest_recent(tmp_path: Path) -> None:
    artifact_catalog.append_catalog_entry(
        tmp_path,
        kind="incident",
        artifact_id="inc-1",
        relative_path="glow/forge/incidents/a.json",
        schema_name="incident",
        schema_version=1,
        links={"incident_id": "inc-1", "quarantine_activated": True},
        summary={"severity": "enforced"},
        ts="2026-01-01T00:00:00Z",
    )
    artifact_catalog.append_catalog_entry(
        tmp_path,
        kind="incident",
        artifact_id="inc-2",
        relative_path="glow/forge/incidents/b.json",
        schema_name="incident",
        schema_version=1,
        links={"incident_id": "inc-2"},
        summary={"severity": "warning"},
        ts="2026-01-01T00:01:00Z",
    )
    assert artifact_catalog.latest(tmp_path, "incident") is not None
    assert len(artifact_catalog.recent(tmp_path, "incident", limit=1)) == 1
    quarantine = artifact_catalog.latest_quarantine_incident(tmp_path)
    assert quarantine is not None
    assert quarantine["id"] == "inc-1"


def test_goal_and_plan_run_links_survive_catalog_normalization(tmp_path: Path) -> None:
    row = artifact_catalog.append_catalog_entry(
        tmp_path, kind="work_run", artifact_id="run-1",
        relative_path="glow/forge/work_runs/run-1.json", schema_name="",
        schema_version=3,
        links={"goal_ids": ["g2", "g1"], "work_plan_id": "plan-1",
            "work_run_id": "run-1", "unrecognized": "drop"},
    )

    assert row["links"] == {
        "goal_ids": ["g1", "g2"], "work_plan_id": "plan-1",
        "work_run_id": "run-1",
    }


def test_linkage_incident_to_pack_to_run(tmp_path: Path) -> None:
    trace_payload = {
        "trace_id": "trace_1",
        "created_at": "2026-01-01T00:00:00Z",
        "context": "forge_run",
        "final_decision": "hold",
        "final_reason": "audit_chain_broken",
        "reason_stack": ["audit_chain_broken"],
        "operating_mode": "recovery",
        "strategic_posture": "stability",
        "integrity_pressure_level": 4,
        "integrity_metrics_summary": {},
        "gates_evaluated": [],
        "quarantine_state_summary": {"active": True, "last_incident_id": "inc-1"},
    }
    emitted = emit_pack_from_trace(tmp_path, trace_payload=trace_payload, trace_path="glow/forge/traces/t.json")
    assert emitted is not None
    pack_id = str(emitted["pack_id"])
    run_payload = {
        "schema_version": 1,
        "run_id": "run_1",
        "generated_at": "2026-01-01T00:05:00Z",
        "pack_id": pack_id,
        "pack_path": str(emitted["pack_path"]),
        "status": "completed",
        "steps": [],
    }
    run_path = tmp_path / f"glow/forge/remediation/runs/run_20260101T000500Z_{pack_id}.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps(run_payload, sort_keys=True) + "\n", encoding="utf-8")
    artifact_catalog.append_catalog_entry(
        tmp_path,
        kind="remediation_run",
        artifact_id="run_1",
        relative_path=str(run_path.relative_to(tmp_path)),
        schema_name="remediation_run",
        schema_version=1,
        links={"pack_id": pack_id, "run_id": "run_1", "incident_id": "inc-1"},
        summary={"status": "completed"},
        ts="2026-01-01T00:05:00Z",
    )
    assert artifact_catalog.latest_for_incident(tmp_path, "inc-1", kind="remediation_pack") is not None
    assert artifact_catalog.latest_successful_remediation_run(tmp_path, pack_id) is not None


def test_rebuild_guard_and_report(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    incident = build_incident(triggers=["x"], enforcement_mode="warn", severity="warning", created_at="2026-01-01T00:00:00Z")
    write_incident(tmp_path, incident)
    monkeypatch.setenv("SENTIENTOS_ALLOW_CATALOG_REBUILD", "1")
    report = artifact_catalog.rebuild_catalog_from_disk(tmp_path)
    assert report["appended_entries"] >= 0
    assert (tmp_path / str(report["report_path"])).exists()


def test_quarantine_clear_prefers_catalog(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/quarantine.json").write_text(
        '{"schema_version":1,"active":true,"activated_at":"2026-01-01T00:00:00Z","last_incident_id":"inc-1","freeze_forge":true,"allow_automerge":false,"allow_publish":false,"allow_federation_sync":true,"notes":[]}\n',
        encoding="utf-8",
    )
    artifact_catalog.append_catalog_entry(
        tmp_path,
        kind="remediation_pack",
        artifact_id="pack-cat",
        relative_path="glow/forge/remediation/packs/pack_pack-cat.json",
        schema_name="remediation_pack",
        schema_version=1,
        links={"incident_id": "inc-1", "pack_id": "pack-cat"},
        summary={"status": "queued"},
        ts="2026-01-01T00:01:00Z",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust/state.json"))
    from sentientos.control_plane_kernel import reset_control_plane_kernel
    from sentientos.federated_governance import reset_controller as reset_federated_governance
    from sentientos.runtime_governor import reset_runtime_governor
    from sentientos.trust_ledger import reset_trust_ledger
    from sentientos.pulse_trust_epoch import reset_manager as reset_trust_epoch_manager
    reset_federated_governance()
    reset_runtime_governor()
    reset_trust_ledger()
    reset_trust_epoch_manager()
    reset_control_plane_kernel()
    monkeypatch.setattr("scripts.quarantine_clear.verify_receipt_chain", lambda root: type("R", (), {"ok": True, "to_dict": lambda self: {"status": "ok"}})())
    monkeypatch.setattr("scripts.quarantine_clear.verify_receipt_anchors", lambda root: type("A", (), {"ok": True, "to_dict": lambda self: {"status": "ok"}})())
    monkeypatch.setattr("scripts.quarantine_clear.verify_doctrine_identity", lambda root: (True, {"ok": True}))
    monkeypatch.setattr("scripts.quarantine_clear.federation_integrity_gate", lambda root, context: {"blocked": False, "status": "ok"})
    monkeypatch.setattr("scripts.quarantine_clear.maybe_verify_audit_chain", lambda root, context: (None, False, False, None))

    assert quarantine_clear.main([]) == 0


def test_resolve_entry_path_uses_redirect_mapping(tmp_path: Path) -> None:
    (tmp_path / "glow/forge/archive").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/archive/redirects.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-01-01T00:00:00Z",
                "old_path": "glow/forge/orchestrator/ticks/tick_old.json",
                "new_path": "glow/forge/archive/tick/2026/01/tick_old.json",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    entry = {"path": "glow/forge/orchestrator/ticks/tick_old.json"}
    assert artifact_catalog.resolve_entry_path(tmp_path, entry) == "glow/forge/archive/tick/2026/01/tick_old.json"


def test_catalog_queries_ignore_malformed_nested_json_metadata(tmp_path: Path) -> None:
    catalog_path = tmp_path / "pulse/artifact_catalog.jsonl"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        json.dumps({
            "kind": "incident",
            "id": "incident-1",
            "ts": "2026-01-01T00:00:00Z",
            "links": ["malformed"],
        })
        + "\n"
        + json.dumps({
            "kind": "remediation_run",
            "id": "run-1",
            "ts": "2026-01-01T00:01:00Z",
            "links": None,
            "summary": ["malformed"],
        })
        + "\n",
        encoding="utf-8",
    )

    assert artifact_catalog.latest_quarantine_incident(tmp_path) is None
    assert artifact_catalog.latest_for_incident(
        tmp_path, "incident-1", kind="incident",
    ) is None
    assert artifact_catalog.latest_successful_remediation_run(tmp_path, "pack-1") is None


def test_rebuild_rejects_non_integer_catalog_schema_version(
    tmp_path: Path, monkeypatch,
) -> None:
    malformed_entry: dict[str, object] = {
        "kind": "incident",
        "id": "incident-1",
        "path": "glow/forge/incidents/incident-1.json",
        "schema_name": "incident",
        "schema_version_artifact": "1",
    }
    monkeypatch.setattr(artifact_catalog, "_entries", lambda _root: [])
    monkeypatch.setattr(
        artifact_catalog,
        "_discover_entries",
        lambda _root, **_kwargs: [malformed_entry],
    )

    with pytest.raises(ValueError, match="catalog_schema_version_must_be_integer"):
        artifact_catalog.rebuild_catalog_from_disk(tmp_path)
