from __future__ import annotations

import json
from pathlib import Path

from scripts import system_constitution
from sentientos.attestation import read_json, write_json
from sentientos.system_constitution import (
    CONSTITUTION_TRANSITIONS_REL,
    compose_system_constitution,
    write_constitution_artifacts,
)


def _seed_required(root: Path, *, posture: str = "nominal", degraded_audit: bool = False, compromise_mode: bool = False) -> None:
    write_json(root / "vow/immutable_manifest.json", {"manifest": "ok", "schema_version": 1})
    (root / "vow/invariants.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "vow/invariants.yaml").write_text("invariants: []\n", encoding="utf-8")

    write_json(
        root / "glow/runtime/audit_trust_state.json",
        {
            "status": "ok",
            "history_state": "intact_trusted",
            "degraded_audit_trust": degraded_audit,
            "checkpoint_id": None,
            "continuation_descends_from_anchor": True,
            "trusted_history_head_hash": "abc",
            "report_break_count": 0,
            "trust_boundary_explicit": True,
        },
    )
    write_json(
        root / "glow/governor/rollup.json",
        {
            "mode": "enforce",
            "runtime_posture_summary": {"nominal": 2, "constrained": 0, "restricted": 0} if posture == "nominal" else {posture: 3},
            "class_summary": {"federated_control": {}, "control_plane_task": {}},
        },
    )
    (root / "glow/governor/observability.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (root / "glow/governor/observability.jsonl").write_text(
        json.dumps({"runtime_posture": {"reason_chain": [{"restriction_class": "audit_trust"}, {"restriction_class": "none"}]}}) + "\n",
        encoding="utf-8",
    )
    write_json(root / "glow/governor/storm_budget.json", {"control_plane_task_counts": {"control_plane_task": 1}})
    write_json(
        root / "glow/pulse_trust/epoch_state.json",
        {"active_epoch_id": "epoch-0001", "compromise_response_mode": compromise_mode, "transition_counter": 1, "revoked_epochs": []},
    )
    write_json(root / "glow/federation/governance_digest.json", {"digest": "digest-1", "components": {"schema_version": 1}})
    write_json(root / "glow/federation/federation_quorum_policy.json", {"requirements": {"high": 2}})
    write_json(root / "glow/federation/peer_governance_digests.json", {"peers": []})
    write_json(
        root / "glow/federation/trust_ledger_state.json",
        {
            "peer_count": 1,
            "state_summary": {"trusted": 1, "watched": 0, "degraded": 0, "quarantined": 0, "incompatible": 0},
            "peer_states": [{"peer_id": "peer-a", "trust_state": "trusted", "trust_reasons": ["ok"], "reconciliation_needed": False}],
        },
    )


def test_compose_constitution_deterministic_and_digest_stable(tmp_path: Path) -> None:
    _seed_required(tmp_path)

    payload_1 = compose_system_constitution(tmp_path)
    payload_2 = compose_system_constitution(tmp_path)

    assert payload_1 == payload_2
    assert payload_1["constitutional_digest"] == payload_2["constitutional_digest"]
    assert payload_1["exit_code"] == 0
    assert payload_1["constitution_state"] == "healthy"


def test_constitution_state_classification(tmp_path: Path) -> None:
    _seed_required(tmp_path)
    assert compose_system_constitution(tmp_path)["exit_code"] == 0

    _seed_required(tmp_path, posture="constrained")
    degraded_payload = compose_system_constitution(tmp_path)
    assert degraded_payload["constitution_state"] == "degraded"
    assert degraded_payload["exit_code"] == 1

    _seed_required(tmp_path, degraded_audit=True)
    restricted_payload = compose_system_constitution(tmp_path)
    assert restricted_payload["constitution_state"] == "restricted"
    assert restricted_payload["exit_code"] == 2

    (tmp_path / "glow/runtime/audit_trust_state.json").unlink()
    missing_payload = compose_system_constitution(tmp_path)
    assert missing_payload["constitution_state"] == "missing"
    assert missing_payload["exit_code"] == 3


def test_artifact_resolution_stability(tmp_path: Path) -> None:
    _seed_required(tmp_path)
    payload = compose_system_constitution(tmp_path)

    refs = payload["constitutional_refs"]["artifact_paths"]
    assert refs["immutable_manifest"]["path"] == "vow/immutable_manifest.json"
    assert refs["governor_rollup"]["path"] == "glow/governor/rollup.json"
    assert refs["pulse_trust_epoch"]["path"] == "glow/pulse_trust/epoch_state.json"


def test_cli_exit_codes(tmp_path: Path, monkeypatch: object, capsys: object) -> None:
    _seed_required(tmp_path)
    monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]

    assert system_constitution.main(["--verify"]) == 0
    assert system_constitution.main(["--json"]) == 0

    _seed_required(tmp_path, degraded_audit=True)
    assert system_constitution.main(["--verify"]) == 2

    (tmp_path / "glow/runtime/audit_trust_state.json").unlink()
    assert system_constitution.main(["--verify"]) == 3

    out = capsys.readouterr().out  # type: ignore[union-attr]
    assert "verify=" in out


def test_constitution_transition_log_is_bounded(tmp_path: Path) -> None:
    _seed_required(tmp_path)
    transitions_path = tmp_path / CONSTITUTION_TRANSITIONS_REL
    transitions_path.parent.mkdir(parents=True, exist_ok=True)
    with transitions_path.open("w", encoding="utf-8") as handle:
        for i in range(700):
            handle.write(json.dumps({"constitutional_digest": f"d{i}"}, sort_keys=True) + "\n")

    payload = compose_system_constitution(tmp_path)
    write_constitution_artifacts(tmp_path, payload=payload)

    rows = transitions_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) <= 512
    stored = read_json(tmp_path / "glow/constitution/system_constitution.json")
    assert stored["constitutional_digest"] == payload["constitutional_digest"]
